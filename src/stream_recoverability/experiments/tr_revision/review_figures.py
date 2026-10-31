"""Four manuscript figures generated from published aggregate tables.

This is figure-level reproduction, not refitting or raw-data validation.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from stream_recoverability.experiments.tr_revision.cohort_denominators import (
    two_method_intersection,
)

COLORS = ["#315a7d", "#ca743c", "#48918a", "#97648b"]


def set_review_style():
    plt.rcParams.update({"font.family":"Liberation Sans", "font.size":11,
        "axes.titlesize":11, "axes.labelsize":10.5, "xtick.labelsize":9.5,
        "ytick.labelsize":9.5, "legend.fontsize":8.5, "axes.spines.top":False,
        "axes.spines.right":False, "pdf.fonttype":42, "figure.facecolor":"white"})


def require_group_intervals(uncertainty_ci, requests):
    """Every plotted coverage series needs one finite group interval.

    A missing table or row must stop the figure. Omitting the interval and
    drawing the point alone is not a valid recreation of the manuscript figure.
    """
    if uncertainty_ci is None:
        raise ValueError(
            "Group-interval table is required; the figure must not omit intervals"
        )
    missing = []
    for family, mode, estimator, dependence in requests:
        rows = uncertainty_ci.loc[
            uncertainty_ci.family.eq(family)
            & uncertainty_ci["mode"].eq(mode)
            & uncertainty_ci.estimator.eq(estimator)
            & uncertainty_ci.dependence.eq(dependence)
        ]
        if len(rows) != 1 or not np.isfinite([rows.iloc[0].low, rows.iloc[0].high]).all():
            missing.append(f"{family}/{mode}/{estimator}/{dependence}")
    if missing:
        raise ValueError(
            "Group-interval table is missing required rows: " + ", ".join(missing)
        )


def plot_aggregate_figures(
    score,
    trend,
    factor,
    annual,
    states,
    releases,
    save,
    trend_cases=None,
    uncertainty=None,
    uncertainty_ci=None,
    uncertainty_cases=None,
):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    methods = [
        "plug_in",
        "functional_debias",
        "distribution_regression",
        "stochastic_regression_calibrated",
    ]
    labels = ["Plug-in", "Debias", "D2", "Stochastic"]
    b = (
        score.loc[score.family.eq("crossed") & score.stratum.eq("danger")]
        .set_index("estimator")
        .loc[methods]
    )
    axes[0].bar(np.arange(4), b.mae_median, color=COLORS)
    axes[0].errorbar(
        np.arange(4),
        b.mae_median,
        yerr=np.vstack([b.mae_median - b.mae_lower, b.mae_upper - b.mae_median]),
        fmt="none",
        ecolor="0.25",
        capsize=3,
    )
    axes[0].set(
        xticks=np.arange(4),
        xticklabels=labels,
        ylabel="H30 MAE (C)",
        title="Point accuracy",
    )
    axes[1].bar(
        [0, 1], b.loc[methods[-2:], "coverage90_median"] * 100, color=COLORS[2:]
    )
    axes[1].axhline(90, color="0.35", ls="--", lw=1)
    axes[1].set(
        xticks=[0, 1],
        xticklabels=labels[-2:],
        ylabel="Coverage (%)",
        ylim=(0, 100),
        title="Calibration",
    )
    save(fig, "02_annual_comparators")

    settings = [
        ("calendar", "offline"),
        ("crossed", "offline"),
        ("calendar", "forward"),
        ("crossed", "forward"),
    ]
    names = [
        "Cal.\noffline",
        "Ctrl.\noffline",
        "Cal.\nforward",
        "Ctrl.\nforward",
    ]
    if trend_cases is None:
        raise ValueError(
            "Common-cohort case table is required; summary-only denominators are not used"
        )
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 4.15))
    factor_names = []
    pair_counts = []
    for i, (family, mode) in enumerate(settings):
        rows = trend_cases.loc[
            trend_cases.family.eq(family)
            & trend_cases["mode"].eq(mode)
            & trend_cases.estimator.eq("D2")
            & trend_cases.dependence.eq("point")
            & trend_cases.available
        ]
        pivot = rows.pivot_table(
            index=["station_key", "replicate"],
            columns="retention",
            values="squared_error",
            aggfunc="mean",
        )
        common = pivot[["all", "warm90"]].dropna()
        all_rmse = float(np.sqrt(common["all"].mean()))
        warm_rmse = float(np.sqrt(common["warm90"].mean()))
        n_all = int(pivot["all"].notna().sum())
        n_warm = int(pivot["warm90"].notna().sum())
        n_common = int(len(common))
        units = rows.drop_duplicates(["station_key", "replicate"])
        stations = int(units.station_key.nunique())
        groups = (
            int(units.independence_group.nunique())
            if "independence_group" in units
            else 0
        )
        axes[0].bar(
            i - 0.18,
            warm_rmse,
            width=0.34,
            color="0.72",
            label="Warm-season" if i == 0 else None,
        )
        axes[0].bar(
            i + 0.18,
            all_rmse,
            width=0.34,
            color=COLORS[0],
            label="Retain all + D2" if i == 0 else None,
        )
        axes[0].annotate(
            f"{n_common}/{n_all}\n{stations} st, {groups} gr",
            (i + 0.18, all_rmse),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.2,
        )
        axes[0].annotate(
            f"{n_common}/{n_all}",
            (i - 0.18, warm_rmse),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.2,
        )
        for j, estimator in enumerate(["D2", "stochastic_calibrated"]):
            row = factor.loc[
                factor.family.eq(family)
                & factor["mode"].eq(mode)
                & factor.estimator.eq(estimator)
            ].iloc[0]
            x = i + (-0.18 if j == 0 else 0.18)
            retention = 100 * row.retention_fraction
            axes[1].bar(x, retention, width=0.32, color=COLORS[0])
            axes[1].bar(
                x, 100 - retention, bottom=retention, width=0.32, color=COLORS[1]
            )
        subset = factor.loc[factor.family.eq(family) & factor["mode"].eq(mode)]
        n_d2 = int(subset.loc[subset.estimator.eq("D2"), "n_paired"].iloc[0])
        n_classic = int(
            subset.loc[subset.estimator.eq("stochastic_calibrated"), "n_paired"].iloc[0]
        )
        factor_names.append(names[i])
        pair_counts.append((n_d2, n_classic))
    axes[0].set(
        xticks=range(4),
        xticklabels=names,
        ylabel="Trend RMSE (C/dec)",
        title="Whole-archive trend error\n(common station-repetition rows)",
    )
    axes[0].set_yscale("log")
    axes[0].yaxis.set_major_formatter(mticker.FormatStrFormatter("%g"))
    axes[0].yaxis.set_minor_formatter(mticker.NullFormatter())
    axes[0].legend(frameon=False, fontsize=8.5)
    axes[1].set(
        xticks=range(4),
        xticklabels=factor_names,
        ylabel="MSE gain (%)",
        ylim=(0, 118),
        title="Retention vs estimator\n($n$ above bars: D2, then classical)",
    )
    for i, (n_d2, n_classic) in enumerate(pair_counts):
        axes[1].text(
            i,
            101.2,
            f"{n_d2}\n{n_classic}",
            ha="center",
            va="bottom",
            fontsize=6.4,
            linespacing=0.9,
        )
    from matplotlib.patches import Patch

    axes[1].legend(
        handles=[
            Patch(color=COLORS[0], label="Retention"),
            Patch(color=COLORS[1], label="Estimator"),
        ],
        frameon=False,
        fontsize=8.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.46),
        ncol=2,
    )
    save(fig, "03_archive_factorial")

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 4.35))
    if uncertainty is not None:
        if uncertainty_cases is None:
            raise ValueError(
                "The paired annual panel needs the two-method case table"
            )
        paired = two_method_intersection(uncertainty_cases)
        paired = paired.loc[paired.family.eq("crossed")].set_index("mode")
        for j, (column, equal, label) in enumerate(
            [
                ("annual_weighted_d2", "annual_equal_d2", "D2"),
                ("annual_weighted_classic", "annual_equal_classic", "Classical"),
            ]
        ):
            x = np.arange(2) + (j - 0.5) * 0.34
            axes[0].bar(
                x,
                paired.loc[["offline", "forward"], column] * 100,
                width=0.32,
                color=COLORS[j],
                label=label,
            )
            axes[0].scatter(
                x,
                paired.loc[["offline", "forward"], equal] * 100,
                marker="_",
                color="0.15",
                s=55,
                zorder=3,
            )
        tick_labels = []
        for mode, short in [("offline", "Offline"), ("forward", "Forward")]:
            row = paired.loc[mode]
            own = uncertainty.loc[
                uncertainty.family.eq("crossed") & uncertainty["mode"].eq(mode)
            ].set_index("estimator")
            tick_labels.append(
                f"{short}\npaired $n$={int(row.n_paired)}\n"
                f"D2 {int(row.n_own_d2)}/{int(own.loc['D2'].n_all)}; "
                f"Cl. {int(row.n_own_classic)}/{int(own.loc['stochastic_calibrated'].n_all)}"
            )
        axes[0].axhline(90, color="0.4", ls="--", lw=1)
        axes[0].set(
            xticks=[0, 1],
            xticklabels=tick_labels,
            ylabel="Annual coverage (%)",
            ylim=(78, 102),
            title="Paired annual coverage\n(intersection; 90% nominal)",
        )
        axes[0].tick_params(axis="x", labelsize=6.8)
        axes[0].legend(
            frameon=False,
            fontsize=7.5,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.58),
            ncol=2,
        )
        interval_requests = [
            ("crossed", mode, estimator, dependence)
            for dependence in ["independent", "shared_parameters", "residual_blocks"]
            for mode in ["offline", "forward"]
            for estimator in ["D2", "stochastic_calibrated"]
        ]
        require_group_intervals(uncertainty_ci, interval_requests)
        positions = np.arange(4)
        labels = ["D2\noff", "Cl.\noff", "D2\nfwd", "Cl.\nfwd"]
        ns = []
        for mode in ["offline", "forward"]:
            for estimator in ["D2", "stochastic_calibrated"]:
                row = uncertainty.loc[
                    uncertainty.family.eq("crossed")
                    & uncertainty["mode"].eq(mode)
                    & uncertainty.estimator.eq(estimator)
                ].iloc[0]
                ns.append(int(row.n_common))
        for j, dependence in enumerate(
            ["independent", "shared_parameters", "residual_blocks"]
        ):
            values, lower, upper = [], [], []
            for mode in ["offline", "forward"]:
                for estimator in ["D2", "stochastic_calibrated"]:
                    row = uncertainty.loc[
                        uncertainty.family.eq("crossed")
                        & uncertainty["mode"].eq(mode)
                        & uncertainty.estimator.eq(estimator)
                    ].iloc[0]
                    value = 100 * row[f"{dependence}_coverage95"]
                    values.append(value)
                    if uncertainty_ci is not None:
                        ci = uncertainty_ci.loc[
                            uncertainty_ci.family.eq("crossed")
                            & uncertainty_ci["mode"].eq(mode)
                            & uncertainty_ci.estimator.eq(estimator)
                            & uncertainty_ci.dependence.eq(dependence)
                        ]
                        if len(ci):
                            lower.append(value - 100 * ci.iloc[0].low)
                            upper.append(100 * ci.iloc[0].high - value)
            yerr = (
                np.vstack([lower, upper])
                if uncertainty_ci is not None and len(lower) == len(values)
                else None
            )
            axes[1].errorbar(
                positions + (j - 1) * 0.08,
                values,
                yerr=yerr,
                fmt="o-",
                color=COLORS[j],
                ms=5,
                capsize=2,
                lw=1,
                label=["Independent", "Shared", "Blocks"][j],
            )
        axes[1].axhline(95, color="0.5", ls="--", lw=1)
        axes[1].set(
            xticks=positions,
            xticklabels=[f"{label}\n$n$={n}" for label, n in zip(labels, ns)],
            ylabel="Trend coverage (%)",
            ylim=(74, 101),
            title="Each method's available set\n(not paired; 95% nominal)",
        )
        axes[1].legend(frameon=False, fontsize=7.5, loc="lower left")
    else:
        for j, estimator in enumerate(["D2", "stochastic_calibrated"]):
            b = annual.loc[
                annual.family.eq("crossed") & annual.estimator.eq(estimator)
            ].set_index("mode")
            axes[0].bar(
                np.arange(2) + (j - 0.5) * 0.34,
                b.loc[["offline", "forward"], "mean_station_coverage90"] * 100,
                width=0.32,
                color=COLORS[j],
                label="D2" if j == 0 else "Stochastic",
            )
        axes[0].axhline(90, color="0.4", ls="--", lw=1)
        axes[0].set(
            xticks=[0, 1],
            xticklabels=["Offline", "Forward"],
            ylabel="Coverage (%)",
            ylim=(0, 100),
            title="Annual marginals",
        )
        axes[0].legend(
            frameon=False,
            fontsize=8.5,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.2),
            ncol=3,
        )
        for j, dependence in enumerate(
            ["independent", "shared_parameters", "residual_blocks"]
        ):
            values = []
            for mode in ["offline", "forward"]:
                for estimator in ["D2", "stochastic_calibrated"]:
                    row = trend.loc[
                        trend.family.eq("crossed")
                        & trend["mode"].eq(mode)
                        & trend.estimator.eq(estimator)
                        & trend.dependence.eq(dependence)
                    ].iloc[0]
                    values.append(100 * row.missing_coverage95)
            axes[1].plot(
                np.arange(4) + (j - 1) * 0.08,
                values,
                "o-",
                color=COLORS[j],
                ms=5,
                label=["Independent", "Shared", "Blocks"][j],
            )
        axes[1].axhline(95, color="0.5", ls="--", lw=1)
        axes[1].set(
            xticks=range(4),
            xticklabels=["D2\noff", "Stoch.\noff", "D2\nfwd", "Stoch.\nfwd"],
            ylabel="Trend coverage (%)",
            ylim=(65, 100),
            title="Joint ranks",
        )
        axes[1].legend(frameon=False, fontsize=8.5, loc="lower left")
    save(fig, "04_joint_uncertainty")

    conditions = ["clean", "hot_year_extrapolation", "future_years", "air_exposure"]
    labels = ["Clean", "Hot", "Future", "Air"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    b = states.loc[states.family.eq("calendar")].set_index("condition").loc[conditions]
    bottom = np.zeros(4)
    for column, label, color in [
        ("estimate_fraction", "Estimate", COLORS[0]),
        ("bound_fraction", "Bound", COLORS[2]),
        ("unknown_fraction", "Unknown", "0.8"),
    ]:
        values = 100 * b[column].to_numpy()
        axes[0].bar(range(4), values, bottom=bottom, label=label, color=color)
        bottom += values
    axes[0].set(
        xticks=range(4),
        xticklabels=labels,
        ylabel="Cases (%)",
        title="Empirical calendars",
    )
    axes[0].legend(
        frameon=False,
        fontsize=8.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=3,
    )
    for i, condition in enumerate(conditions):
        b = releases.loc[
            releases.family.eq("crossed") & releases.condition.eq(condition)
        ].set_index("method")
        for method, marker in [("fixed_risk", "o"), ("three_outputs", "s")]:
            row = b.loc[method]
            if pd.notna(row.risk):
                axes[1].scatter(
                    row.retention * 100,
                    row.risk * 100,
                    color=COLORS[i],
                    marker=marker,
                    s=55,
                )
        if pd.notna(b.loc["three_outputs", "risk"]):
            row = b.loc["three_outputs"]
            axes[1].annotate(
                labels[i],
                (row.retention * 100, row.risk * 100),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8.5,
            )
        else:
            row = b.loc["fixed_risk"]
            axes[1].annotate(
                labels[i],
                (row.retention * 100, row.risk * 100),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8.5,
            )
    axes[1].set(
        xlabel="Values published (%)",
        ylabel="Selected error (%)",
        title="Controlled gaps",
        xlim=(0, 100),
        ylim=(0, 45),
    )
    axes[1].text(
        0.03,
        0.95,
        "Circle: fixed cap\nSquare: three outputs\nNo square: zero published",
        transform=axes[1].transAxes,
        va="top",
        fontsize=8.5,
    )
    save(fig, "05_output_boundaries")
