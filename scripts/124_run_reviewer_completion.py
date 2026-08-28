#!/usr/bin/env python3
"""Run the reviewer-requested v11 baselines, adaptation, and real replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stream_recoverability.analysis.advanced_validation import (
    calibration_components,
    evaluate_risk_control,
    interval_metrics,
    mondrian_intervals,
    network_block_scaled_intervals,
    recalibration_budget_curve,
    risk_control_threshold,
)
from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    read_temperature_panel,
)
from stream_recoverability.experiments.empirical_placement import (
    pairwise_replay_losses,
    placement_replay_curve,
    training_correlation,
)
from stream_recoverability.experiments.recovery_roster import (
    empirical_transfer_predictions,
    fitting_period_empirical_losses,
    score_model_roster_on_placements,
)

OUTPUT = ROOT / "results/development_v11/reviewer_completion"
DEV_PLACEMENTS = ROOT / "results/development_v11/recovery_scoring/placement_losses.csv"
DEV_OUTCOMES = ROOT / "results/development_v11/station_gap_outcomes.csv"
DEV_LONO = ROOT / "results/development_v11/nested_lono_predictions.csv"
INVENTORY = ROOT / "results/development_v11/network_inventory.csv"
CONFIRMATION = ROOT / "results/development_v11/route_a_confirmation"


def _json_safe(value: object) -> object:
    """Convert numpy scalars and non-finite floats to strict JSON values."""

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if np.isfinite(numeric) else None
    return value


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"network_id": str, "station_id": str})


def _development_panel(network: str, role: str) -> pd.DataFrame:
    path = (
        ROOT
        / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
        / role
        / "networks"
        / network
        / "daily_wide_qc.csv"
    )
    return read_temperature_panel(str(path))


def _confirmation_panel(network: str) -> pd.DataFrame:
    return read_temperature_panel(
        str(
            CONFIRMATION.parent
            / "confirmation_daily_qc/networks"
            / network
            / "daily_wide_temperature.csv"
        )
    )


def _append_xgboost_roster(placements: pd.DataFrame) -> pd.DataFrame:
    frame = placements.loc[placements["information_condition"].eq("B_union_D")].copy()
    frame["model_family"] = "xgboost_b_d"
    frame["season"] = pd.to_datetime(frame["gap_start"]).dt.month.map(
        lambda month: (
            "DJF"
            if month in (12, 1, 2)
            else "MAM"
            if month in (3, 4, 5)
            else "JJA"
            if month in (6, 7, 8)
            else "SON"
        )
    )
    return frame[
        [
            "network_id",
            "station_id",
            "gap_length",
            "placement",
            "gap_start",
            "season",
            "model_family",
            "mae_deg_c",
            "rmse_deg_c",
            "training_years",
            "evaluation_years",
        ]
    ]


def _run_recovery_roster(
    inventory: pd.DataFrame,
    development_placements: pd.DataFrame,
    confirmation_placements: pd.DataFrame,
    *,
    n_jobs: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    parameters = {**XGBOOST_PARAMETERS, "n_jobs": n_jobs}
    dev_roster = [_append_xgboost_roster(development_placements)]
    dev_empirical = []
    matched = set(_read_csv(DEV_OUTCOMES)["network_id"])
    roles = inventory.set_index("network_id")["role"].to_dict()
    for ordinal, network in enumerate(sorted(matched), start=1):
        print(
            f"development recovery roster {ordinal}/{len(matched)}: {network}",
            flush=True,
        )
        panel = _development_panel(network, str(roles[network]))
        dev_roster.append(
            score_model_roster_on_placements(network, panel, development_placements)
        )
        dev_empirical.append(
            fitting_period_empirical_losses(
                network,
                panel,
                development_placements,
                xgboost_parameters=parameters,
            )
        )

    confirm_roster = [_append_xgboost_roster(confirmation_placements)]
    confirm_empirical = []
    confirmation_networks = sorted(confirmation_placements["network_id"].unique())
    for ordinal, network in enumerate(confirmation_networks, start=1):
        print(
            f"confirmation recovery roster {ordinal}/{len(confirmation_networks)}: {network}",
            flush=True,
        )
        panel = _confirmation_panel(network)
        confirm_roster.append(
            score_model_roster_on_placements(network, panel, confirmation_placements)
        )
        confirm_empirical.append(
            fitting_period_empirical_losses(
                network,
                panel,
                confirmation_placements,
                xgboost_parameters=parameters,
            )
        )
    return (
        pd.concat(dev_roster, ignore_index=True),
        pd.concat(dev_empirical, ignore_index=True),
        pd.concat(confirm_roster, ignore_index=True),
        pd.concat(confirm_empirical, ignore_index=True),
    )


def _empirical_station_gap(
    empirical: pd.DataFrame, placements: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    placement_prediction = empirical_transfer_predictions(empirical, placements)
    summary = placement_prediction.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
        observed_recovery_loss=("mae_deg_c", "mean"),
        n_placements=("placement", "size"),
        empirical_transfer_supported=("empirical_transfer_supported", "all"),
    )
    summary["empirical_transfer_source"] = np.where(
        summary["empirical_transfer_supported"],
        "within_horizon_training_curve",
        "network_mean_fallback",
    )
    return placement_prediction, summary


def _weighted_fit(train: pd.DataFrame, columns: list[str], outcome: str) -> np.ndarray:
    counts = train.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack(
        [np.ones(len(train)), train[columns].to_numpy(dtype=float)]
    )
    return np.linalg.lstsq(
        design * root_weight[:, None],
        train[outcome].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]


def _roster_invariance(
    development_roster: pd.DataFrame,
    confirmation_roster: pd.DataFrame,
    development_predictors: pd.DataFrame,
    confirmation_predictors: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = [
        "gap_length",
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
        "nearest_donor_correlation",
    ]
    rows = []
    predictions = []
    for family in sorted(development_roster["model_family"].unique()):
        dev_loss = (
            development_roster.loc[development_roster["model_family"].eq(family)]
            .groupby(["network_id", "station_id", "gap_length"], as_index=False)[
                "mae_deg_c"
            ]
            .mean()
            .rename(columns={"mae_deg_c": "model_loss"})
        )
        conf_loss = (
            confirmation_roster.loc[confirmation_roster["model_family"].eq(family)]
            .groupby(["network_id", "station_id", "gap_length"], as_index=False)[
                "mae_deg_c"
            ]
            .mean()
            .rename(columns={"mae_deg_c": "model_loss"})
        )
        dev = (
            development_predictors.drop(
                columns=["observed_recovery_loss"], errors="ignore"
            )
            .merge(dev_loss, on=["network_id", "station_id", "gap_length"])
            .dropna(subset=columns)
        )
        conf = (
            confirmation_predictors.drop(
                columns=["observed_recovery_loss"], errors="ignore"
            )
            .merge(conf_loss, on=["network_id", "station_id", "gap_length"])
            .dropna(subset=columns)
        )
        coefficient = _weighted_fit(dev, columns, "model_loss")
        conf_prediction = (
            coefficient[0] + conf[columns].to_numpy(dtype=float) @ coefficient[1:]
        )
        conf = conf.assign(predicted_model_loss=conf_prediction, model_family=family)
        predictions.append(conf)
        network = conf.groupby("network_id")[
            ["predicted_model_loss", "model_loss"]
        ].mean()
        design = np.column_stack([np.ones(len(conf)), conf_prediction])
        weight = np.sqrt(
            1.0 / conf.groupby("network_id")["network_id"].transform("size").to_numpy()
        )
        intercept, slope = np.linalg.lstsq(
            design * weight[:, None], conf["model_loss"].to_numpy() * weight, rcond=None
        )[0]
        rows.append(
            {
                "model_family": family,
                "development_networks": dev["network_id"].nunique(),
                "confirmation_networks": conf["network_id"].nunique(),
                "confirmation_station_gap_spearman": float(
                    spearmanr(conf_prediction, conf["model_loss"]).statistic
                ),
                "confirmation_network_spearman": float(
                    spearmanr(
                        network["predicted_model_loss"], network["model_loss"]
                    ).statistic
                ),
                "confirmation_calibration_intercept": float(intercept),
                "confirmation_calibration_slope": float(slope),
            }
        )
    return pd.DataFrame(rows), pd.concat(predictions, ignore_index=True)


def _error_model_lono(
    frame: pd.DataFrame, base: list[str], operator: str
) -> pd.DataFrame:
    rows = []
    usable = frame.dropna(subset=[*base, operator, "observed_recovery_loss"])
    for held in sorted(usable["network_id"].unique()):
        train = usable.loc[~usable["network_id"].eq(held)]
        test = usable.loc[usable["network_id"].eq(held)]
        for name, columns in (
            ("learned_error_without_operator", base),
            ("learned_error_with_operator", [*base, operator]),
        ):
            model = HistGradientBoostingRegressor(
                max_iter=150, max_leaf_nodes=15, learning_rate=0.05, random_state=0
            )
            model.fit(train[columns], train["observed_recovery_loss"])
            prediction = model.predict(test[columns])
            rows.append(
                pd.DataFrame(
                    {
                        "network_id": held,
                        "station_id": test["station_id"].to_numpy(),
                        "gap_length": test["gap_length"].to_numpy(),
                        "model": name,
                        "prediction": prediction,
                        "observed_recovery_loss": test[
                            "observed_recovery_loss"
                        ].to_numpy(),
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def _prediction_metrics(
    frame: pd.DataFrame, prediction: str, outcome: str
) -> dict[str, float]:
    usable = frame[["network_id", prediction, outcome]].dropna()
    network = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), usable[prediction]])
    intercept, slope = np.linalg.lstsq(
        design * weight[:, None],
        usable[outcome].to_numpy(dtype=float) * weight,
        rcond=None,
    )[0]
    return {
        "n": len(usable),
        "n_networks": len(network),
        "spearman": float(spearmanr(usable[prediction], usable[outcome]).statistic),
        "network_spearman": float(
            spearmanr(network[prediction], network[outcome]).statistic
        ),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "r2": float(r2_score(usable[outcome], usable[prediction])),
        "rmse": float(
            np.sqrt(np.mean(np.square(usable[outcome] - usable[prediction])))
        ),
    }


def _heterogeneity_metrics(
    frame: pd.DataFrame,
    *,
    model: str,
    prediction: str,
    outcome: str,
) -> pd.DataFrame:
    """Descriptive moderator analysis with explicit small-stratum counts."""

    analysis = frame.copy()
    station_counts = analysis.groupby("network_id")["station_id"].transform("nunique")
    analysis["network_size_group"] = pd.cut(
        station_counts,
        bins=[0, 4, 7, np.inf],
        labels=["3_to_4", "5_to_7", "8_plus"],
    ).astype(str)
    rows = []
    for moderator in (
        "provider",
        "domain_group",
        "thermal_state_shift",
        "network_size_group",
    ):
        if moderator not in analysis:
            continue
        for level, values in analysis.groupby(moderator, dropna=False):
            metrics = _prediction_metrics(values, prediction, outcome)
            rows.append(
                {
                    "model": model,
                    "moderator": moderator,
                    "level": str(level),
                    **metrics,
                    "descriptive_only": True,
                }
            )
    return pd.DataFrame(rows)


def _risk_budget_curve(
    frame: pd.DataFrame, *, repeats: int = 100, seed: int = 0
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for domain, group in frame.groupby("domain_group"):
        networks = np.asarray(sorted(group["network_id"].unique()))
        for repeat in range(repeats):
            order = rng.permutation(networks)
            for budget in (25, 50, 100, 200):
                chosen = []
                count = 0
                for network in order:
                    chosen.append(network)
                    count += int(group["network_id"].eq(network).sum())
                    if count >= budget:
                        break
                calibration = group.loc[group["network_id"].isin(chosen)]
                evaluation = group.loc[~group["network_id"].isin(chosen)]
                if evaluation.empty:
                    continue
                rule = risk_control_threshold(calibration, risk_column="predicted_loss")
                result = evaluate_risk_control(
                    evaluation, rule, risk_column="predicted_loss"
                )
                rows.append(
                    {
                        "domain_group": domain,
                        "repeat": repeat,
                        "requested_budget": budget,
                        "labelled_rows": len(calibration),
                        "labelled_networks": calibration["network_id"].nunique(),
                        **result,
                    }
                )
    return pd.DataFrame(rows)


def _mechanism_table(development: pd.DataFrame, lono: pd.DataFrame) -> pd.DataFrame:
    merged = development.merge(
        lono[["network_id", "station_id", "gap_length", "simple_prediction"]],
        on=["network_id", "station_id", "gap_length"],
    )
    counts = merged.groupby(["network_id", "station_id"])["gap_length"].nunique()
    complete = counts[counts.eq(merged["gap_length"].nunique())].index
    fixed = merged.set_index(["network_id", "station_id"]).loc[complete].reset_index()
    result = fixed.groupby("gap_length", as_index=False).agg(
        n_stations=("station_id", "size"),
        conditional_variance_lower_bound=("complete_operator_risk", "mean"),
        simple_prediction=("simple_prediction", "mean"),
        realized_loss=("observed_recovery_loss", "mean"),
    )
    result["model_and_drift_remainder"] = np.maximum(
        0.0, result["realized_loss"] - result["conditional_variance_lower_bound"]
    )
    return result


def _run_placement_replay(
    inventory: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    max_networks: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched = _read_csv(DEV_OUTCOMES)
    station_counts = matched.groupby("network_id")["station_id"].nunique()
    eligible_ids = set(station_counts.loc[station_counts.ge(5)].index)
    candidates = inventory.loc[
        inventory["qualified_open_role"] & inventory["network_id"].isin(eligible_ids)
    ].sort_values("network_id")
    if max_networks is not None:
        candidates = candidates.head(max_networks)
    pairwise_parts = []
    curve_parts = []
    for item in candidates.itertuples(index=False):
        print(f"placement replay: {item.network_id}", flush=True)
        panel = _development_panel(str(item.network_id), str(item.role))
        pairwise = pairwise_replay_losses(str(item.network_id), panel, placements)
        if pairwise.empty:
            continue
        correlation = training_correlation(panel)
        try:
            curve = placement_replay_curve(pairwise, correlation, random_repeats=100)
        except ValueError:
            continue
        curve.insert(0, "network_id", str(item.network_id))
        pairwise_parts.append(pairwise)
        curve_parts.append(curve)
    return pd.concat(pairwise_parts, ignore_index=True), pd.concat(
        curve_parts, ignore_index=True
    )


def _plot_figures(
    confirmation: pd.DataFrame,
    mechanism: pd.DataFrame,
    replay: pd.DataFrame,
    recalibration: pd.DataFrame,
    output: Path,
) -> None:
    colors = {"united_states": "#0072B2", "cross_domain": "#D55E00"}
    figure, axis = plt.subplots(figsize=(10, 3.6))
    stages = [
        "Fitting-period\ndescriptors",
        "Cross-network\nloss calibration",
        "New-network\nrank + interval",
        "Placement /\ntriage decision",
    ]
    for index, label in enumerate(stages):
        axis.text(
            index,
            0,
            label,
            ha="center",
            va="center",
            bbox={"boxstyle": "round,pad=.5", "fc": "#E8F1F8", "ec": "#355C7D"},
        )
        if index:
            axis.annotate(
                "",
                (index - 0.28, 0),
                (index - 0.72, 0),
                arrowprops={"arrowstyle": "->", "lw": 1.5},
            )
    axis.text(
        0, -0.48, "gap length • memory • donor redundancy", ha="center", fontsize=9
    )
    axis.text(
        1,
        -0.48,
        "conditional variance retained as a lower bound",
        ha="center",
        fontsize=9,
    )
    axis.set(xlim=(-0.6, 3.6), ylim=(-0.8, 0.55))
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(output / "figure_01_workflow.png", dpi=300)
    plt.close(figure)

    figure, (axis, residual_axis) = plt.subplots(
        2, 1, figsize=(7.2, 7.2), gridspec_kw={"height_ratios": [4, 1]}, sharex=True
    )
    for group, values in confirmation.groupby("domain_group"):
        axis.scatter(
            values["predicted_loss"],
            values["observed_recovery_loss"],
            s=10,
            alpha=0.22,
            color=colors[group],
            label=group.replace("_", " "),
        )
    medians = confirmation.groupby("network_id")[
        ["predicted_loss", "observed_recovery_loss"]
    ].median()
    axis.scatter(
        medians["predicted_loss"],
        medians["observed_recovery_loss"],
        s=38,
        facecolor="white",
        edgecolor="black",
        linewidth=0.7,
        label="network medians",
    )
    high = max(
        confirmation["predicted_loss"].max(),
        confirmation["observed_recovery_loss"].max(),
    )
    axis.plot([0.03, high], [0.03, high], color="black", lw=1)
    axis.set(
        xscale="log",
        yscale="log",
        ylabel="Realized MAE (°C)",
        title="Ranking transfers, while magnitude calibration shifts by domain",
    )
    axis.legend(frameon=False, fontsize=8)
    residual_axis.scatter(
        confirmation["predicted_loss"],
        confirmation["observed_recovery_loss"] - confirmation["predicted_loss"],
        s=8,
        alpha=0.2,
        color="#555555",
    )
    residual_axis.axhline(0, color="black", lw=1)
    residual_axis.set(xlabel="Predicted MAE (°C, log scale)", ylabel="Residual")
    figure.tight_layout()
    figure.savefig(output / "figure_02_confirmation_calibration.png", dpi=300)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(6.8, 4.8))
    axis.plot(
        mechanism["gap_length"],
        mechanism["conditional_variance_lower_bound"],
        marker="o",
        label="conditional-variance lower bound",
    )
    axis.plot(
        mechanism["gap_length"],
        mechanism["simple_prediction"],
        marker="s",
        label="simple model",
    )
    axis.plot(
        mechanism["gap_length"],
        mechanism["realized_loss"],
        marker="^",
        label="realized loss",
    )
    axis.set(
        xscale="log",
        xlabel="Gap length (days, log scale)",
        ylabel="MAE or risk scale (°C)",
        title="Conditional risk saturates while realized long-gap loss grows",
    )
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(output / "figure_03_mechanism.png", dpi=300)
    plt.close(figure)

    summary = replay.groupby(["policy", "protected_fraction"], as_index=False)[
        "regret"
    ].mean()
    figure, axis = plt.subplots(figsize=(7.2, 5.0))
    for policy, values in summary.groupby("policy"):
        if policy != "oracle":
            axis.plot(
                values["protected_fraction"],
                values["regret"],
                marker="o",
                ms=3,
                label=policy.replace("_", " "),
            )
    axis.axhline(0, color="black", lw=1)
    axis.set(
        xlabel="Retained station fraction",
        ylabel="Worst-target MAE regret (°C)",
        title="Real-data leave-k-station-out replay",
    )
    axis.legend(frameon=False, fontsize=7)
    figure.tight_layout()
    figure.savefig(output / "figure_04_placement_replay.png", dpi=300)
    plt.close(figure)

    budget = recalibration.groupby(
        ["domain_group", "requested_budget"], as_index=False
    ).agg(
        success=("slope_in_target_band", "mean"), slope=("evaluation_slope", "median")
    )
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    for group, values in confirmation.groupby("domain_group"):
        bins = pd.qcut(
            values["predicted_loss"],
            q=min(6, values["predicted_loss"].nunique()),
            duplicates="drop",
        )
        reliability = values.groupby(bins, observed=True)[
            ["predicted_loss", "observed_recovery_loss"]
        ].mean()
        axes[0].plot(
            reliability["predicted_loss"],
            reliability["observed_recovery_loss"],
            marker="o",
            color=colors[group],
            label=group.replace("_", " "),
        )
    axes[0].plot([0, 5], [0, 5], color="black", lw=1)
    axes[0].set(
        xlabel="Mean predicted MAE",
        ylabel="Mean realized MAE",
        title="Domain reliability",
    )
    axes[0].legend(frameon=False)
    for group, values in budget.groupby("domain_group"):
        axes[1].plot(
            values["requested_budget"],
            values["success"],
            marker="o",
            color=colors[group],
            label=group.replace("_", " "),
        )
    axes[1].set(
        xlabel="Requested labelled station-gap budget",
        ylabel="Fraction with slope in [0.9, 1.1]",
        ylim=(-0.02, 1.02),
        title="Post-confirmation adaptation cost",
    )
    figure.tight_layout()
    figure.savefig(output / "figure_05_domain_adaptation.png", dpi=300)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--skip-recovery", action="store_true")
    parser.add_argument("--skip-placement", action="store_true")
    parser.add_argument("--max-placement-networks", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    inventory = _read_csv(INVENTORY)
    dev_placements = _read_csv(DEV_PLACEMENTS)
    conf_placements = _read_csv(CONFIRMATION / "placement_losses.csv")
    if not args.skip_recovery:
        dev_roster, dev_empirical, conf_roster, conf_empirical = _run_recovery_roster(
            inventory, dev_placements, conf_placements, n_jobs=args.n_jobs
        )
        dev_roster.to_csv(
            args.output / "development_model_roster_losses.csv", index=False
        )
        dev_empirical.to_csv(
            args.output / "development_empirical_fit_losses.csv", index=False
        )
        conf_roster.to_csv(
            args.output / "confirmation_model_roster_losses.csv", index=False
        )
        conf_empirical.to_csv(
            args.output / "confirmation_empirical_fit_losses.csv", index=False
        )
    else:
        dev_roster = _read_csv(args.output / "development_model_roster_losses.csv")
        dev_empirical = _read_csv(args.output / "development_empirical_fit_losses.csv")
        conf_roster = _read_csv(args.output / "confirmation_model_roster_losses.csv")
        conf_empirical = _read_csv(
            args.output / "confirmation_empirical_fit_losses.csv"
        )

    dev_empirical_placement, dev_empirical_summary = _empirical_station_gap(
        dev_empirical, dev_placements
    )
    conf_empirical_placement, conf_empirical_summary = _empirical_station_gap(
        conf_empirical, conf_placements
    )
    dev_empirical_placement.to_csv(
        args.output / "development_empirical_predictions.csv", index=False
    )
    conf_empirical_placement.to_csv(
        args.output / "confirmation_empirical_predictions.csv", index=False
    )
    supported_dev = dev_empirical_summary.loc[
        dev_empirical_summary["empirical_transfer_supported"]
    ]
    supported_conf = conf_empirical_summary.loc[
        conf_empirical_summary["empirical_transfer_supported"]
    ]
    empirical_metrics = pd.DataFrame(
        [
            {
                "phase": "development",
                "scope": "supported_only",
                **_prediction_metrics(
                    supported_dev,
                    "empirical_transfer_prediction",
                    "observed_recovery_loss",
                ),
            },
            {
                "phase": "confirmation",
                "scope": "supported_only",
                **_prediction_metrics(
                    supported_conf,
                    "empirical_transfer_prediction",
                    "observed_recovery_loss",
                ),
            },
            {
                "phase": "development",
                "scope": "all_cells_with_network_mean_fallback",
                **_prediction_metrics(
                    dev_empirical_summary,
                    "empirical_transfer_prediction",
                    "observed_recovery_loss",
                ),
            },
            {
                "phase": "confirmation",
                "scope": "all_cells_with_network_mean_fallback",
                **_prediction_metrics(
                    conf_empirical_summary,
                    "empirical_transfer_prediction",
                    "observed_recovery_loss",
                ),
            },
        ]
    )
    empirical_metrics.to_csv(
        args.output / "empirical_transfer_metrics.csv", index=False
    )
    empirical_coverage = conf_empirical_summary.groupby(
        "empirical_transfer_source", as_index=False
    ).agg(
        n_station_gaps=("station_id", "size"),
        n_networks=("network_id", "nunique"),
    )
    empirical_coverage["fraction_of_1440"] = empirical_coverage["n_station_gaps"] / len(
        conf_empirical_summary
    )
    empirical_coverage.to_csv(
        args.output / "empirical_transfer_coverage_audit.csv", index=False
    )

    dev_predictors = _read_csv(DEV_OUTCOMES)
    conf_predictors = _read_csv(CONFIRMATION / "predictions.csv")
    roster_metrics, roster_predictions = _roster_invariance(
        dev_roster, conf_roster, dev_predictors, conf_predictors
    )
    roster_metrics.to_csv(args.output / "model_roster_metrics.csv", index=False)
    roster_predictions.to_csv(args.output / "model_roster_predictions.csv", index=False)

    empirical_feature = dev_empirical_summary[
        ["network_id", "station_id", "gap_length", "empirical_transfer_prediction"]
    ]
    learned_frame = dev_predictors.merge(
        empirical_feature, on=["network_id", "station_id", "gap_length"]
    )
    learned_predictions = _error_model_lono(
        learned_frame,
        [
            "gap_length",
            "acf_only",
            "donor_r2_only",
            "additive_d_over_4_heuristic",
            "nearest_donor_correlation",
            "empirical_transfer_prediction",
        ],
        "complete_operator_risk",
    )
    learned_predictions.to_csv(
        args.output / "learned_error_model_predictions.csv", index=False
    )
    learned_metrics = []
    for name, values in learned_predictions.groupby("model"):
        learned_metrics.append(
            {
                "model": name,
                **_prediction_metrics(values, "prediction", "observed_recovery_loss"),
            }
        )
    learned_metrics = pd.DataFrame(learned_metrics)
    learned_metrics.to_csv(args.output / "learned_error_model_metrics.csv", index=False)

    development_lono = _read_csv(DEV_LONO)
    confirmation = _read_csv(CONFIRMATION / "predictions.csv")
    empirical_with_metadata = conf_empirical_summary.merge(
        confirmation[
            [
                "network_id",
                "station_id",
                "gap_length",
                "provider",
                "domain_group",
                "thermal_state_shift",
            ]
        ],
        on=["network_id", "station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    heterogeneity = pd.concat(
        [
            _heterogeneity_metrics(
                confirmation,
                model="simple_descriptors",
                prediction="predicted_loss",
                outcome="observed_recovery_loss",
            ),
            _heterogeneity_metrics(
                empirical_with_metadata,
                model="fitting_period_empirical_all_cells",
                prediction="empirical_transfer_prediction",
                outcome="observed_recovery_loss",
            ),
        ],
        ignore_index=True,
    )
    heterogeneity.to_csv(args.output / "heterogeneity_metrics.csv", index=False)
    conformal = mondrian_intervals(
        development_lono,
        confirmation,
        calibration_prediction="simple_prediction",
        evaluation_prediction="predicted_loss",
        strata=("horizon_bin",),
        coverage=0.90,
    )
    conformal.to_csv(args.output / "mondrian_confirmation_predictions.csv", index=False)
    conformal_summary = interval_metrics(conformal)
    placement_intervals = conf_placements.drop(
        columns=["observed_recovery_loss"], errors="ignore"
    ).merge(
        conformal[
            [
                "network_id",
                "station_id",
                "gap_length",
                "predicted_loss",
                "prediction_lower",
                "prediction_upper",
                "domain_group",
            ]
        ],
        on=["network_id", "station_id", "gap_length"],
    )
    placement_intervals["season"] = pd.to_datetime(
        placement_intervals["gap_start"]
    ).dt.month.map(
        lambda month: (
            "DJF"
            if month in (12, 1, 2)
            else "MAM"
            if month in (3, 4, 5)
            else "JJA"
            if month in (6, 7, 8)
            else "SON"
        )
    )
    placement_intervals = placement_intervals.rename(
        columns={"mae_deg_c": "observed_recovery_loss"}
    )
    interval_strata = []
    for stratum, column in (
        ("horizon", "gap_length"),
        ("season", "season"),
        ("domain", "domain_group"),
    ):
        for value, values in placement_intervals.groupby(column):
            interval_strata.append(
                {
                    "stratum": stratum,
                    "value": value,
                    **interval_metrics(values),
                }
            )
    pd.DataFrame(interval_strata).to_csv(
        args.output / "interval_metrics_by_horizon_season_domain.csv", index=False
    )
    decomposition = calibration_components(confirmation)
    pd.DataFrame([decomposition]).to_csv(
        args.output / "rank_decomposition.csv", index=False
    )
    recalibration = recalibration_budget_curve(confirmation, repeats=100)
    recalibration.to_csv(args.output / "recalibration_budget_curve.csv", index=False)
    simple_risk_budget = _risk_budget_curve(confirmation)
    simple_risk_budget["risk_model"] = "simple_descriptors"
    empirical_risk_frame = conf_empirical_summary.rename(
        columns={"empirical_transfer_prediction": "predicted_loss"}
    ).merge(
        confirmation[["network_id", "domain_group"]].drop_duplicates(),
        on="network_id",
    )
    empirical_risk_budget = _risk_budget_curve(empirical_risk_frame)
    empirical_risk_budget["risk_model"] = "fitting_period_empirical"
    risk_budget = pd.concat(
        [simple_risk_budget, empirical_risk_budget], ignore_index=True
    )
    risk_budget.to_csv(args.output / "risk_control_budget_curve.csv", index=False)

    empirical_block = network_block_scaled_intervals(
        supported_dev,
        supported_conf.rename(
            columns={"empirical_transfer_prediction": "predicted_loss"}
        ),
        calibration_prediction="empirical_transfer_prediction",
        evaluation_prediction="predicted_loss",
        coverage=0.90,
        scale_power=0.70,
    )
    empirical_block.to_csv(
        args.output / "empirical_network_block_intervals.csv", index=False
    )
    empirical_block_summary = interval_metrics(empirical_block)

    mechanism = _mechanism_table(dev_predictors, development_lono)
    mechanism.to_csv(args.output / "mechanism_decomposition.csv", index=False)
    if not args.skip_placement:
        pairwise, replay = _run_placement_replay(
            inventory, dev_placements, max_networks=args.max_placement_networks
        )
        pairwise.to_csv(args.output / "placement_pairwise_losses.csv", index=False)
        replay.to_csv(args.output / "placement_replay_curve.csv", index=False)
    else:
        replay = _read_csv(args.output / "placement_replay_curve.csv")

    _plot_figures(confirmation, mechanism, replay, recalibration, args.output)
    replay_summary = replay.groupby("policy")["regret"].mean().to_dict()
    recalibration_summary = (
        recalibration.groupby(["domain_group", "requested_budget"])[
            "slope_in_target_band"
        ]
        .mean()
        .rename("success_fraction")
        .reset_index()
        .to_dict(orient="records")
    )
    risk_summary = (
        risk_budget.groupby(["risk_model", "domain_group", "requested_budget"])
        .agg(
            certified_fraction=(
                "status",
                lambda values: float(np.mean(values.eq("certified"))),
            ),
            median_safe_fill_fraction=("safe_fill_fraction", "median"),
            median_false_release_rate=("false_release_rate", "median"),
        )
        .reset_index()
        .to_dict(orient="records")
    )
    readiness_path = ROOT / "results/development_v11/second_confirmation/readiness.json"
    if readiness_path.is_file():
        second_confirmation = json.loads(readiness_path.read_text(encoding="utf-8"))
    else:
        second_confirmation = {
            "status": "not_run_requires_new_independent_networks",
            "minimum_independent_networks_required": 60,
        }
    summary = {
        "evidence_roles": {
            "empirical_transfer": "fitting_period_only_then_outer_evaluation",
            "model_roster": "development_selected_then_first_confirmation_sensitivity",
            "mondrian_interval": "development_only_calibration_on_first_confirmation",
            "domain_recalibration": "post_confirmation_label_budget_analysis",
            "risk_control": "post_confirmation_label_budget_analysis",
            "placement_replay": "open_development_realized_outcomes",
        },
        "empirical_transfer": empirical_metrics.to_dict(orient="records"),
        "empirical_transfer_coverage": empirical_coverage.to_dict(orient="records"),
        "heterogeneity": heterogeneity.to_dict(orient="records"),
        "model_roster": roster_metrics.to_dict(orient="records"),
        "learned_error_models": learned_metrics.to_dict(orient="records"),
        "mondrian_interval": conformal_summary,
        "empirical_network_block_interval": empirical_block_summary,
        "rank_decomposition": decomposition,
        "placement_mean_regret": {
            str(key): float(value) for key, value in replay_summary.items()
        },
        "placement_replay_networks": int(replay["network_id"].nunique()),
        "recalibration_budget": recalibration_summary,
        "risk_control_budget": risk_summary,
        "second_confirmation": second_confirmation,
    }
    strict_summary = _json_safe(summary)
    (args.output / "summary.json").write_text(
        json.dumps(strict_summary, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(strict_summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
