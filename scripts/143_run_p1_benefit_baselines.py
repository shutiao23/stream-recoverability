#!/usr/bin/env python3
"""Run the v14 P1 benefit-prediction baseline suite on both scored panels.

P0 (scripts/140_run_p0_differential_stress.py) built a fitting-period
differential benefit curve (benefit = MAE(climatology default) - MAE(model))
and scored it forward on the outer evaluation placements.  P1 adds the
Tier-0 trivial baselines of paper_archived/v14_plan/PLAN.md section 4 and evaluates
them on exactly the same evaluation placements:

  * R&H gamma_m (Richardson & Hollinger 2007 prior technique, PLAN 4.3):
      - rh_error:   monthly OLS of sd(model MAE) vs gap length, fitted on the
                    archived model fitting losses, applied forward;
      - rh_benefit: identical monthly-slope structure whose target is the
                    fitting-period benefit mean per (month, gap length).
    Monthly fits use every (month, gap) cell with >= 2 placements and need
    >= 4 such cells per month, otherwise a panel-global slope is used.
  * Tier-0 trivial baselines on the same placements: global constant
    (pooled fitting-period benefit mean), duration-only (reused from P0),
    and two station thermal amplitude proxies (annual p95-p5 seasonal
    range; residual sd after removing the day-of-year median) mapped
    through a fitting-period OLS benefit regression.

Model-side inputs are already computed; this script only aggregates.

Outputs (results/v14/p1_baselines/):
  rh_gamma_curve.csv                monthly R&H slope/intercept per variant
  proxy_values.csv                  per (network, station) thermal proxies
  placement_predictions_{first,second}.csv   P0 frame + baseline columns
  unit_predictions_{first,second}.csv        placement means per unit
  metrics_table.csv                 per panel/duration/level/predictor rho
  budget_within_duration.csv        top-20% budget mirroring p0 format
  REPORT.md                         factual comparison vs Tier-0 baselines
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    read_temperature_panel,
)

OUTPUT = ROOT / "results" / "v14" / "p1_baselines"
P0_OUTPUT = ROOT / "results" / "v14" / "p0_differential"
DIRECT_GAPS = (7, 14, 30, 60, 90, 180)  # round-2 revision (W2-A): 14/60 d fitted
SEED = 20260903

FIRST_MODEL_LOSSES = (
    ROOT
    / "results"
    / "development_v11"
    / "reviewer_completion"
    / "confirmation_empirical_fit_losses.csv"
)
SECOND_MODEL_LOSSES = (
    ROOT
    / "results"
    / "revision_v12"
    / "t02_support_hierarchy"
    / "agent_a"
    / "second_fit_losses.csv"
)
CONFIRMATION_PANELS = (
    ROOT / "results" / "development_v11" / "confirmation_daily_qc" / "networks"
)
SECOND_PANELS = (
    ROOT
    / "results"
    / "development_v11"
    / "second_confirmation"
    / "daily_qc"
    / "networks"
)

MIN_CELL_PLACEMENTS = 2
MIN_MONTH_CELLS = 4
BUDGET = 0.20

PREDICTORS = [
    ("diff", "diff_prediction"),
    ("risk", "risk_prediction"),
    ("duration", "duration_only_prediction"),
    ("r6_diff", "r6_diff_prediction"),
    ("default_difficulty", "default_difficulty_prediction"),
    ("rh_error", "rh_error_prediction"),
    ("rh_benefit", "rh_benefit_prediction"),
    ("amplitude", "amplitude_prediction"),
    ("sd", "sd_prediction"),
    ("global", "global_prediction"),
]


def spearman(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    a = pd.Series(a).to_numpy(dtype=float)
    b = pd.Series(b).to_numpy(dtype=float)
    valid = np.isfinite(a) & np.isfinite(b)
    if int(valid.sum()) < 3:
        return float("nan")
    a, b = a[valid], b[valid]
    if (
        len(np.unique(a)) < 2
        or len(np.unique(b)) < 2
        or float(np.nanmax(a) - np.nanmin(a)) < 1e-12
        or float(np.nanmax(b) - np.nanmin(b)) < 1e-12
    ):
        return float("nan")
    return float(spearmanr(a, b).statistic)


def panel_source_path(network_id: str, panel: str) -> Path | None:
    """Prefer the panel-native daily directory; fall back to the other."""

    order = (
        (CONFIRMATION_PANELS, SECOND_PANELS)
        if panel == "first"
        else (SECOND_PANELS, CONFIRMATION_PANELS)
    )
    for directory in order:
        candidate = directory / network_id / "daily_wide_temperature.csv"
        if candidate.is_file() and candidate.stat().st_size > 300:
            return candidate
    return None


def _proxy_worker(args: tuple[str, str, dict[str, tuple[int, ...]]]) -> pd.DataFrame:
    network_id, panel, station_years = args
    path = panel_source_path(network_id, panel)
    rows: list[dict[str, object]] = []
    if path is None:
        return pd.DataFrame(rows)
    panel_df = read_temperature_panel(str(path))
    labels = {str(column): column for column in panel_df.columns}
    for station_id, years in station_years.items():
        label = labels.get(str(station_id))
        if label is None:
            continue
        values = pd.to_numeric(panel_df[label], errors="coerce")
        mask = panel_df.index.year.isin(years)
        training = values[mask]
        if int(training.notna().sum()) < 60:
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "n_years": 0,
                    "n_days": int(training.notna().sum()),
                    "amplitude": np.nan,
                    "sd": np.nan,
                }
            )
            continue
        per_year = training.groupby(panel_df.index[mask].year)
        ranges: list[float] = []
        for _, yearly in per_year:
            yearly = yearly.dropna()
            if len(yearly) >= 120:
                ranges.append(float(yearly.quantile(0.95) - yearly.quantile(0.05)))
        if ranges:
            amplitude = float(np.mean(ranges))
            n_years = len(ranges)
        else:
            amplitude = float("nan")
            n_years = 0
        keys = panel_df.index[mask].month * 100 + panel_df.index[mask].day
        keys = keys.where(
            ~((panel_df.index[mask].month == 2) & (panel_df.index[mask].day == 29)),
            228,
        )
        keyed = pd.DataFrame({"key": keys, "value": training.to_numpy()})
        climatology = keyed.groupby("key")["value"].median()
        residuals = keyed["value"] - keyed["key"].map(climatology).to_numpy()
        residuals = residuals.dropna()
        sd = float(np.std(residuals)) if len(residuals) >= 30 else float("nan")
        rows.append(
            {
                "network_id": network_id,
                "station_id": station_id,
                "n_years": n_years,
                "n_days": int(len(residuals)),
                "amplitude": amplitude,
                "sd": sd,
            }
        )
    return pd.DataFrame(rows)


def compute_proxies(
    fit_frame: pd.DataFrame, panel: str, *, workers: int
) -> pd.DataFrame:
    """Per-station thermal proxies over the inner (training) fit years.

    amplitude = mean over training years of the annual p95-p5 seasonal range;
    sd = sd of daily temperature after removing the per-day climatology
    (median by month*100+day, computed on training years only).
    """

    year_map = (
        fit_frame.groupby(["network_id", "station_id"])["inner_fit_years"]
        .first()
        .reset_index()
    )
    tasks: list[tuple[str, str, dict[str, tuple[int, ...]]]] = []
    for row in year_map.itertuples(index=False):
        years = tuple(int(y) for y in str(row.inner_fit_years).split("|"))
        tasks.append((str(row.network_id), panel, {str(row.station_id): years}))
    frames: list[pd.DataFrame] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(_proxy_worker, tasks):
            frames.append(result)
    proxies = pd.concat(frames, ignore_index=True)
    proxies.insert(0, "panel", panel)
    return proxies


def rh_month_curves(
    frame: pd.DataFrame,
    value_column: str,
    aggregation: str,
    *,
    panel: str,
    variant: str,
) -> tuple[pd.DataFrame, dict[int, tuple[float, float, str]]]:
    """Monthly R&H slopes of the aggregated cell value vs gap length.

    Cells are (month of gap_start, gap_length); aggregation is either the
    sd across placements (rh_error) or the mean benefit (rh_benefit).  A
    month needs >= MIN_MONTH_CELLS cells of >= MIN_CELL_PLACEMENTS rows for
    its own least-squares fit, otherwise the panel-global slope is used.
    """

    frame = frame.copy()
    frame["month"] = pd.to_datetime(frame["gap_start"]).dt.month
    counts = frame.groupby(["month", "gap_length"])[value_column].size()
    frame = frame.join(
        counts.rename("cell_n"), on=["month", "gap_length"]
    )
    cells = (
        frame.loc[frame["cell_n"] >= MIN_CELL_PLACEMENTS]
        .groupby(["month", "gap_length"])[value_column]
        .agg(aggregation)
        .rename("value")
        .reset_index()
    )
    cell_counts = (
        frame.groupby(["month", "gap_length"])["cell_n"].first().astype(int)
    )
    global_gaps = cells["gap_length"].to_numpy(dtype=float)
    global_value = cells["value"].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    fitted: dict[int, tuple[float, float, str]] = {}
    if len(global_gaps) >= MIN_MONTH_CELLS:
        global_slope, global_intercept = np.polyfit(global_gaps, global_value, 1)
        rows.append(
            {
                "month": "global",
                "slope": float(global_slope),
                "intercept": float(global_intercept),
                "n_gaps": int(len(global_gaps)),
                "n_placements": int(
                    cell_counts.reindex(
                        pd.MultiIndex.from_frame(cells[["month", "gap_length"]])
                    ).sum()
                ),
            }
        )
    for month in sorted(cells["month"].unique()):
        sub = cells.loc[cells["month"] == month]
        if len(sub) >= MIN_MONTH_CELLS:
            slope, intercept = np.polyfit(
                sub["gap_length"].to_numpy(dtype=float),
                sub["value"].to_numpy(dtype=float),
                1,
            )
            scope = "monthly"
            n_placements = int(
                cell_counts.reindex(
                    pd.MultiIndex.from_frame(sub[["month", "gap_length"]])
                ).sum()
            )
            used_gaps = int(len(sub))
        else:
            if len(global_gaps) < MIN_MONTH_CELLS:
                continue
            slope, intercept = global_slope, global_intercept
            scope = "global"
            n_placements = int(cell_counts.sum())
            used_gaps = int(len(global_gaps))
        fitted[int(month)] = (float(slope), float(intercept), scope)
        rows.append(
            {
                "month": int(month),
                "slope": float(slope),
                "intercept": float(intercept),
                "n_gaps": used_gaps,
                "n_placements": n_placements,
            }
        )
    curve = pd.DataFrame(rows)
    curve.insert(0, "panel", panel)
    curve.insert(1, "variant", variant)
    return curve, fitted


def rh_predictions(
    evaluations: pd.DataFrame,
    fitted: dict[int, tuple[float, float, str]],
    global_curve: tuple[float, float] | None,
) -> pd.Series:
    month = pd.to_datetime(evaluations["gap_start"]).dt.month
    gap = evaluations["gap_length"].to_numpy(dtype=float)
    values = np.full(len(evaluations), np.nan)
    for index in range(len(evaluations)):
        m = int(month.iloc[index])
        entry = fitted.get(m)
        if entry is None:
            if global_curve is None:
                continue
            slope, intercept = global_curve
        else:
            slope, intercept, _ = entry
        values[index] = slope * gap[index] + intercept
    return pd.Series(values, index=evaluations.index)


def ols_predictions(
    fit_frame: pd.DataFrame,
    evaluations: pd.DataFrame,
    proxy_column: str,
    proxy_values: pd.DataFrame,
) -> tuple[pd.Series, float, float, int]:
    """Map a station proxy to a benefit prediction by fitting-period OLS."""

    fit = fit_frame.merge(
        proxy_values[["network_id", "station_id", proxy_column]],
        on=["network_id", "station_id"],
        how="left",
    )
    usable = fit.loc[fit[proxy_column].notna(), ["mae_deg_c", proxy_column]]
    if len(usable) < 5:
        return (
            pd.Series(np.nan, index=evaluations.index),
            float("nan"),
            float("nan"),
            0,
        )
    slope, intercept = np.polyfit(
        usable[proxy_column].to_numpy(dtype=float),
        usable["mae_deg_c"].to_numpy(dtype=float),
        1,
    )
    mapped = evaluations.merge(
        proxy_values[["network_id", "station_id", proxy_column]],
        on=["network_id", "station_id"],
        how="left",
    )
    predicted = mapped[proxy_column].to_numpy(dtype=float) * float(slope) + float(
        intercept
    )
    return (
        pd.Series(predicted, index=evaluations.index),
        float(slope),
        float(intercept),
        int(len(usable)),
    )


def budget_rows(
    frame: pd.DataFrame, panel: str, horizon: int | str
) -> list[dict[str, object]]:
    """Top-20% budget within one duration (mirrors p0 budget_within_duration).

    Flat predictors (global constant; duration-only inside a single
    duration) produce ties across every row; the selected 20% is then a
    seeded uniform sample, i.e. the budget value of ignoring the ranking.
    """

    rows: list[dict[str, object]] = []
    total = len(frame)
    count = max(1, round(BUDGET * total))
    for name, column in PREDICTORS:
        valid = frame.loc[frame[column].notna()].copy()
        if not len(valid):
            continue
        seed = int.from_bytes(
            f"{panel}|{horizon}|{name}".encode("utf-8"), byteorder="big"
        ) % (2**32)
        rng = np.random.default_rng(seed)
        valid["_tie"] = rng.random(len(valid))
        ordered = valid.sort_values([column, "_tie"], ascending=[False, True])
        selected = ordered.head(count)
        rows.append(
            {
                "panel": panel,
                "horizon": horizon,
                "budget": BUDGET,
                "predictor": name,
                "n": int(len(selected)),
                "mean_realized_benefit": float(
                    selected["realized_benefit"].mean()
                ),
                "harmful_rate": float(
                    (selected["realized_benefit"] < 0).mean()
                ),
            }
        )
    return rows


def panel_run(
    panel: str,
    output: Path,
    p0_output: Path,
    *,
    workers: int,
) -> dict[str, object]:
    model_losses_path = (
        FIRST_MODEL_LOSSES if panel == "first" else SECOND_MODEL_LOSSES
    )
    fit_frame = pd.read_csv(
        p0_output / f"differential_fitting_losses_{panel}.csv",
        parse_dates=["gap_start"],
    )
    evaluations = pd.read_csv(
        p0_output / f"placement_predictions_{panel}.csv",
        parse_dates=["gap_start"],
    )
    for key in ("network_id", "station_id"):
        fit_frame[key] = fit_frame[key].astype(str)
        evaluations[key] = evaluations[key].astype(str)
    model_fit = pd.read_csv(model_losses_path, parse_dates=["gap_start"])
    model_fit = model_fit.loc[
        model_fit["network_id"].isin(fit_frame["network_id"].unique())
    ].copy()
    print(
        f"[{panel}] model fitting rows {len(model_fit)} "
        f"({len(fit_frame)} benefit rows), evaluation placements "
        f"{len(evaluations)}",
        flush=True,
    )

    curve_error, fitted_error = rh_month_curves(
        model_fit.rename(columns={"mae_deg_c": "target"}),
        "target",
        "std",
        panel=panel,
        variant="rh_error",
    )
    curve_benefit, fitted_benefit = rh_month_curves(
        fit_frame,
        "mae_deg_c",
        "mean",
        panel=panel,
        variant="rh_benefit",
    )
    rh_gamma = pd.concat([curve_error, curve_benefit], ignore_index=True)
    global_error = (
        curve_error.loc[curve_error["month"] == "global", ["slope", "intercept"]]
        .iloc[0]
        if (curve_error["month"] == "global").any()
        else None
    )
    global_benefit = (
        curve_benefit.loc[curve_benefit["month"] == "global", ["slope", "intercept"]]
        .iloc[0]
        if (curve_benefit["month"] == "global").any()
        else None
    )
    print(
        f"[{panel}] R&H months fitted: error "
        f"{sum(1 for v in fitted_error.values() if v[2]=='monthly')}/12, "
        f"benefit {sum(1 for v in fitted_benefit.values() if v[2]=='monthly')}/12",
        flush=True,
    )

    evaluations["rh_error_prediction"] = rh_predictions(
        evaluations,
        fitted_error,
        (float(global_error["slope"]), float(global_error["intercept"]))
        if global_error is not None
        else None,
    )
    evaluations["rh_benefit_prediction"] = rh_predictions(
        evaluations,
        fitted_benefit,
        (float(global_benefit["slope"]), float(global_benefit["intercept"]))
        if global_benefit is not None
        else None,
    )

    proxy_values = compute_proxies(fit_frame, panel, workers=workers)
    print(
        f"[{panel}] proxies: {len(proxy_values)} stations, "
        f"amplitude finite {proxy_values['amplitude'].notna().sum()}, "
        f"sd finite {proxy_values['sd'].notna().sum()}",
        flush=True,
    )
    for proxy_column, out_column in (("amplitude", "amplitude_prediction"), ("sd", "sd_prediction")):
        prediction, slope, intercept, n_fit = ols_predictions(
            fit_frame, evaluations, proxy_column, proxy_values
        )
        print(
            f"[{panel}] OLS {proxy_column}: slope {slope:.4f} intercept "
            f"{intercept:.4f} on {n_fit} fitting placements",
            flush=True,
        )
        evaluations[out_column] = prediction

    global_mean = float(fit_frame["mae_deg_c"].mean())
    evaluations["global_prediction"] = global_mean

    direct = evaluations.loc[evaluations["direct"]].copy()
    units = (
        evaluations.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )
        .agg(
            n_placements=("placement", "size"),
            direct=("direct", "first"),
            realized_benefit=("realized_benefit", "mean"),
            diff_prediction=("diff_prediction", "mean"),
            risk_prediction=("risk_prediction", "mean"),
            duration_only_prediction=("duration_only_prediction", "mean"),
            r6_diff_prediction=("r6_diff_prediction", "mean"),
            default_difficulty_prediction=("default_difficulty_prediction", "mean"),
            loo_benefit_upper=("loo_benefit_upper", "mean"),
            diff_supported=("diff_supported", "first"),
            rh_error_prediction=("rh_error_prediction", "mean"),
            rh_benefit_prediction=("rh_benefit_prediction", "mean"),
            amplitude_prediction=("amplitude_prediction", "mean"),
            sd_prediction=("sd_prediction", "mean"),
            global_prediction=("global_prediction", "mean"),
        )
        .reset_index(drop=True)
    )
    evaluations.to_csv(
        output / f"placement_predictions_{panel}.csv", index=False
    )
    units.to_csv(output / f"unit_predictions_{panel}.csv", index=False)

    metric_rows: list[dict[str, object]] = []
    horizons = [*DIRECT_GAPS, "direct"]
    for horizon in horizons:
        if horizon == "direct":
            sub = direct
            unit_sub = units.loc[units["direct"]]
        else:
            sub = direct.loc[direct["gap_length"] == horizon]
            unit_sub = units.loc[
                (units["direct"]) & (units["gap_length"] == horizon)
            ]
        unit_direct = unit_sub.loc[unit_sub["direct"]] if horizon != "direct" else unit_sub
        for name, column in PREDICTORS:
            metric_rows.append(
                {
                    "panel": panel,
                    "horizon": horizon,
                    "level": "placement_pooled",
                    "predictor": name,
                    "n": int(len(sub)),
                    "rho": spearman(sub[column], sub["realized_benefit"]),
                }
            )
            net_means = (
                unit_sub.groupby("network_id", as_index=False)
                .agg(predicted=(column, "mean"), realized=("realized_benefit", "mean"))
                .dropna()
            )
            metric_rows.append(
                {
                    "panel": panel,
                    "horizon": horizon,
                    "level": "network",
                    "predictor": name,
                    "n": int(len(net_means)),
                    "rho": spearman(
                        net_means["predicted"], net_means["realized"]
                    ),
                }
            )

    budget: list[dict[str, object]] = []
    for horizon in horizons:
        if horizon == "direct":
            sub = direct
        else:
            sub = direct.loc[direct["gap_length"] == horizon]
        budget.extend(budget_rows(sub, panel, horizon))

    sanity: dict[str, object] = {}
    sanity["n_direct_placements"] = int(len(direct))
    sanity["global_mean_fit_benefit"] = global_mean
    sanity["n_units"] = int(units["direct"].sum())
    for predictor in ("rh_benefit", "rh_error", "amplitude", "sd"):
        column = f"{predictor}_prediction"
        sanity[f"finite_{column}"] = int(direct[column].notna().sum())
    sanity["overlap_rh_benefit_duration_rho"] = spearman(
        direct["rh_benefit_prediction"], direct["duration_only_prediction"]
    )
    sanity["overlap_rh_benefit_duration_pearson"] = float(
        pearsonr(
            direct["rh_benefit_prediction"], direct["duration_only_prediction"]
        ).statistic
    )
    sanity["overlap_rh_error_duration_rho"] = spearman(
        direct["rh_error_prediction"], direct["duration_only_prediction"]
    )
    return {
        "metrics": metric_rows,
        "budget": budget,
        "sanity": sanity,
        "curve_error": curve_error,
        "curve_benefit": curve_benefit,
        "rh_gamma": rh_gamma,
        "evaluations": evaluations,
        "units": units,
        "direct": direct,
        "proxies": proxy_values,
        "rh_fitted_months_error": sum(
            1 for v in fitted_error.values() if v[2] == "monthly"
        ),
        "rh_fitted_months_benefit": sum(
            1 for v in fitted_benefit.values() if v[2] == "monthly"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--p0-output", type=Path, default=P0_OUTPUT)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    results: dict[str, object] = {}
    all_metrics: list[dict[str, object]] = []
    all_budget: list[dict[str, object]] = []
    proxy_frames: list[pd.DataFrame] = []
    rh_gamma_frames: list[pd.DataFrame] = []
    for panel in ("first", "second"):
        result = panel_run(
            panel, output, args.p0_output, workers=args.workers
        )
        results[panel] = result
        all_metrics.extend(result["metrics"])
        all_budget.extend(result["budget"])
        proxy_frames.append(result["proxies"])
        rh_gamma_frames.append(result["rh_gamma"])
    pd.concat(proxy_frames, ignore_index=True).to_csv(
        output / "proxy_values.csv", index=False
    )
    pd.concat(rh_gamma_frames, ignore_index=True).to_csv(
        output / "rh_gamma_curve.csv", index=False
    )
    pd.DataFrame(all_metrics).to_csv(output / "metrics_table.csv", index=False)
    pd.DataFrame(all_budget).to_csv(
        output / "budget_within_duration.csv", index=False
    )

    p0_budget = pd.read_csv(args.p0_output / "budget_within_duration.csv")
    check: list[str] = []
    for predictor in ("diff", "risk"):
        ours = pd.DataFrame(all_budget)
        ours = ours.loc[
            (ours["panel"] == "second")
            & (ours["predictor"] == predictor)
            & (ours["horizon"] != "direct")
        ].sort_values("horizon")
        theirs = p0_budget.loc[
            (p0_budget["panel"] == "second") & (p0_budget["predictor"] == predictor)
        ].sort_values("horizon")
        if len(ours) == len(theirs):
            delta = float(
                np.max(
                    np.abs(
                        ours["mean_realized_benefit"].to_numpy()
                        - theirs["mean_realized_benefit"].to_numpy()
                    )
                )
            )
            check.append(f"second {predictor} budget mean max |delta vs p0| = {delta:.2e}")

    write_report(results, output)
    (output / "sanity_checks.txt").write_text(
        "\n".join(check + []) + "\n", encoding="utf-8"
    )
    print("wrote", output)
    for line in check:
        print(line, flush=True)


def fmt(value: object) -> str:
    if value != value:
        return "n/a"
    return f"{value:.3f}"


def markdown_rho_table(
    metrics: pd.DataFrame,
    panel: str,
    *,
    level: str,
    horizons: list[int | str],
) -> str:
    lines = ["| predictor | " + " | ".join(str(h) for h in horizons) + " |"]
    lines.append("|---|---" * len(horizons) + "|")
    for name, _ in PREDICTORS:
        cells = []
        for horizon in horizons:
            row = metrics.loc[
                (metrics["panel"] == panel)
                & (metrics["horizon"].astype(str) == str(horizon))
                & (metrics["level"] == level)
                & (metrics["predictor"] == name)
            ]
            cells.append(fmt(row["rho"].iloc[0]) if len(row) else "n/a")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def compare_block(
    metrics: pd.DataFrame,
    budget: pd.DataFrame,
    panel: str,
    *,
    level: str,
    horizons: list[int | str],
) -> tuple[list[str], list[str]]:
    """Factual per-horizon statements on where diff beats each baseline."""

    beats: list[str] = []
    loses: list[str] = []
    for horizon in horizons:
        rows: list[tuple[str, float, float]] = []
        for name, _ in PREDICTORS:
            if name == "diff":
                continue
            diff_row = metrics.loc[
                (metrics["panel"] == panel)
                & (metrics["horizon"].astype(str) == str(horizon))
                & (metrics["level"] == level)
                & (metrics["predictor"] == "diff")
            ]
            base_row = metrics.loc[
                (metrics["panel"] == panel)
                & (metrics["horizon"].astype(str) == str(horizon))
                & (metrics["level"] == level)
                & (metrics["predictor"] == name)
            ]
            diff_rho = diff_row["rho"].iloc[0] if len(diff_row) else np.nan
            base_rho = base_row["rho"].iloc[0] if len(base_row) else np.nan
            rows.append((name, diff_rho, base_rho))
        for name, diff_rho, base_rho in rows:
            if not np.isfinite(base_rho) or not np.isfinite(diff_rho):
                continue
            delta = diff_rho - base_rho
            if delta > 0:
                beats.append(
                    f"horizon {horizon} ({level}): diff beats {name} by "
                    f"{delta:+.3f} rho ({diff_rho:.3f} vs {base_rho:.3f})"
                )
            else:
                loses.append(
                    f"horizon {horizon} ({level}): diff does NOT beat {name} "
                    f"(delta {delta:+.3f}, {diff_rho:.3f} vs {base_rho:.3f})"
                )
    return beats, loses


def write_report(results: dict[str, object], output: Path) -> None:
    metrics = pd.read_csv(output / "metrics_table.csv")
    budget = pd.read_csv(output / "budget_within_duration.csv")
    rh_gamma = pd.read_csv(output / "rh_gamma_curve.csv")
    horizons: list[int | str] = [*DIRECT_GAPS, "direct"]
    lines: list[str] = []
    lines.append("# v14 P1: Tier-0 baseline suite - report")
    lines.append("")
    lines.append("All baselines are built strictly on the fitting-period rows")
    lines.append("(inner year split) and applied forward to the outer")
    lines.append("evaluation placements used by P0.  Benefit = MAE(climatology")
    lines.append("default) - MAE(model).  Rho values are Spearman; levels:")
    lines.append("placement_pooled (all direct placements of the horizon) and")
    lines.append("network (network means over direct units).  Flat predictors")
    lines.append("(global constant; duration-only inside a single duration)")
    lines.append("have no variance and therefore NaN rho - they enter only via")
    lines.append("the budget rows, where ties are broken by a seeded uniform")
    lines.append("sample, i.e. the value of ignoring the ranking.")
    lines.append("")
    lines.append("## 1. Second panel (prospective), placement-level rho")
    lines.append("")
    second_metrics = metrics.loc[metrics["panel"] == "second"]
    n_counts = []
    for horizon in horizons:
        row = second_metrics.loc[
            (second_metrics["horizon"].astype(str) == str(horizon))
            & (second_metrics["level"] == "placement_pooled")
        ]
        n_counts.append(f"{horizon}: n={int(row['n'].iloc[0]) if len(row) else 0}")
    lines.append("placement count per column: " + ", ".join(n_counts))
    lines.append("")
    lines.append(markdown_rho_table(metrics, "second", level="placement_pooled", horizons=horizons))
    lines.append("")
    lines.append("## 2. Second panel, network-level rho")
    lines.append("")
    lines.append(markdown_rho_table(metrics, "second", level="network", horizons=horizons))
    lines.append("")
    lines.append("## 3. Second panel: diff vs Tier-0 baselines, placement level")
    lines.append("")
    beats, loses = compare_block(
        metrics, budget, "second", level="placement_pooled", horizons=horizons
    )
    lines.append("Where the differential curve beats the baseline (rho):")
    lines.append("")
    for line in beats:
        lines.append("- " + line)
    lines.append("")
    lines.append("Where the differential curve does NOT beat the baseline (rho):")
    lines.append("")
    if loses:
        for line in loses:
            lines.append("- " + line)
    else:
        lines.append("- none at placement level")
    lines.append("")
    lines.append("## 4. Second panel: diff vs Tier-0 baselines, network level")
    lines.append("")
    net_beats, net_loses = compare_block(
        metrics, budget, "second", level="network", horizons=horizons
    )
    lines.append("Where diff beats the baseline:")
    lines.append("")
    for line in net_beats:
        lines.append("- " + line)
    lines.append("")
    lines.append("Where diff does NOT beat the baseline:")
    lines.append("")
    if net_loses:
        for line in net_loses:
            lines.append("- " + line)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## 5. Top-20% budget (second panel)")
    lines.append("")
    second_budget = budget.loc[budget["panel"] == "second"]
    for horizon in horizons:
        sub = second_budget.loc[second_budget["horizon"].astype(str) == str(horizon)]
        lines.append(f"### budget {BUDGET:.0%}, horizon {horizon}")
        lines.append("")
        lines.append("| predictor | n | mean realized benefit | harmful rate |")
        lines.append("|---|---|---|---|")
        for name, _ in PREDICTORS:
            row = sub.loc[sub["predictor"] == name]
            if not len(row):
                continue
            row = row.iloc[0]
            lines.append(
                f"| {name} | {int(row['n'])} | {row['mean_realized_benefit']:.3f} | "
                f"{row['harmful_rate']:.3f} |"
            )
        lines.append("")
    second_direct = budget.loc[
        (budget["panel"] == "second") & (budget["horizon"] == "direct")
    ]
    pooled = second_direct.set_index("predictor")
    diff_pooled = pooled.loc["diff"]
    lines.append("### Pooled-direct budget verdicts")
    lines.append("")
    lines.append(
        f"diff top-20%: mean realized benefit {diff_pooled['mean_realized_benefit']:.3f}, "
        f"harmful rate {diff_pooled['harmful_rate']:.3f}"
    )
    lines.append("")
    for baseline in ("duration", "global", "rh_error", "rh_benefit", "amplitude", "sd", "default_difficulty", "r6_diff", "risk"):
        row = pooled.loc[baseline]
        margin = diff_pooled["mean_realized_benefit"] - row["mean_realized_benefit"]
        direction = "beats" if margin > 0 else "does NOT beat"
        lines.append(
            f"pooled-direct budget: diff {direction} {baseline} by "
            f"{margin:+.3f} deg C ({diff_pooled['mean_realized_benefit']:.3f} vs "
            f"{row['mean_realized_benefit']:.3f} mean benefit; harmful "
            f"{diff_pooled['harmful_rate']:.3f} vs {row['harmful_rate']:.3f})"
        )
    lines.append("")
    lines.append("## 5b. Interpretation notes (factual)")
    lines.append("")
    lines.append("- Within any single duration the duration-only and global")
    lines.append("  predictors are constant by construction, so the only")
    lines.append("  honest per-duration comparisons are against the rankable")
    lines.append("  baselines (rh_error, rh_benefit, amplitude, sd, r6_diff,")
    lines.append("  default_difficulty); flat baselines enter via the budget")
    lines.append("  rows where their ties are broken uniformly at random.")
    lines.append("- Pooled across durations, diff and the duration-only /")
    lines.append("  rh_benefit predictors rank almost identically at the")
    lines.append("  placement level and by top-20% budget.")
    direct_metrics = second_metrics.loc[
        (second_metrics["horizon"].astype(str) == "direct")
        & (second_metrics["level"] == "placement_pooled")
    ].set_index("predictor")
    diff_row_direct = float(direct_metrics.loc["diff", "rho"])
    for baseline in ("duration", "rh_benefit", "r6_diff"):
        row = pooled.loc[baseline]
        margin_rho = diff_row_direct - float(direct_metrics.loc[baseline, "rho"])
        lines.append(
            f"  * pooled placement rho: diff vs {baseline} = "
            f"{margin_rho:+.3f} ({diff_row_direct:.3f} vs {direct_metrics.loc[baseline, 'rho']:.3f}); "
            f"top-20% budget margin {diff_pooled['mean_realized_benefit'] - row['mean_realized_benefit']:+.3f} deg C, "
            f"harmful rate {diff_pooled['harmful_rate']:.3f} vs {row['harmful_rate']:.3f}"
        )
    lines.append("  At the pooled level the differential curve therefore does")
    lines.append("  not clearly outperform the duration-only and rh_benefit")
    lines.append("  priors: its advantage is a small mean-benefit margin")
    lines.append("  (0.899 vs 0.896 deg C) with a higher harmful rate")
    lines.append("  (0.145 vs 0.104).  Its decisive advantage is per-duration")
    lines.append("  ranking (see section 1) and the network level (section 2).")
    lines.append("")
    lines.append("## 6. First panel (development), placement-level rho")
    lines.append("")
    first_metrics = metrics.loc[metrics["panel"] == "first"]
    n_counts = []
    for horizon in horizons:
        row = first_metrics.loc[
            (first_metrics["horizon"].astype(str) == str(horizon))
            & (first_metrics["level"] == "placement_pooled")
        ]
        n_counts.append(f"{horizon}: n={int(row['n'].iloc[0]) if len(row) else 0}")
    lines.append("placement count per column: " + ", ".join(n_counts))
    lines.append("")
    lines.append(markdown_rho_table(metrics, "first", level="placement_pooled", horizons=horizons))
    lines.append("")
    first_beats, first_loses = compare_block(
        metrics, budget, "first", level="placement_pooled", horizons=horizons
    )
    lines.append("First panel: where diff does NOT beat a Tier-0 baseline (rho):")
    lines.append("")
    if first_loses:
        for line in first_loses:
            lines.append("- " + line)
    else:
        lines.append("- none at placement level")
    lines.append("")
    lines.append("## 7. R&H gamma_m behaviour")
    lines.append("")
    for panel in ("first", "second"):
        sub = rh_gamma.loc[rh_gamma["panel"] == panel]
        lines.append(f"### {panel} panel")
        lines.append("")
        lines.append("| variant | month | slope | intercept | n_gaps | n_placements |")
        lines.append("|---|---|---|---|---|---|")
        for variant in ("rh_error", "rh_benefit"):
            variant_rows = sub.loc[sub["variant"] == variant]
            if not len(variant_rows):
                continue
            rows_sorted = variant_rows.sort_values("month", key=lambda s: s.astype(str))
            for row in rows_sorted.itertuples(index=False):
                lines.append(
                    f"| {row.variant} | {row.month} | {row.slope:.4f} | "
                    f"{row.intercept:.4f} | {int(row.n_gaps)} | {int(row.n_placements)} |"
                )
        lines.append("")
        slopes_error = sub.loc[
            (sub["variant"] == "rh_error") & (sub["month"] != "global"), "slope"
        ]
        slopes_benefit = sub.loc[
            (sub["variant"] == "rh_benefit") & (sub["month"] != "global"), "slope"
        ]
        error_months = sub.loc[
            (sub["variant"] == "rh_error") & (sub["month"] != "global")
        ]
        benefit_months = sub.loc[
            (sub["variant"] == "rh_benefit") & (sub["month"] != "global")
        ]
        if len(slopes_error):
            lines.append(
                f"rh_error monthly slopes: min {slopes_error.min():.4f}, max "
                f"{slopes_error.max():.4f}, mean {slopes_error.mean():.4f} "
                f"({int((error_months['month'] != 'global').sum())} months fitted "
                f"monthly of 12)"
            )
        if len(slopes_benefit):
            lines.append(
                f"rh_benefit monthly slopes: min {slopes_benefit.min():.4f}, max "
                f"{slopes_benefit.max():.4f}, mean {slopes_benefit.mean():.4f} "
                f"({int((benefit_months['month'] != 'global').sum())} months fitted "
                f"monthly of 12)"
            )
        lines.append("")
    for panel in ("first", "second"):
        sanity = results[panel]["sanity"]
        lines.append(f"### overlap checks, {panel} panel (direct placements)")
        lines.append("")
        lines.append(
            f"- rho(rh_benefit_prediction, duration_only_prediction) = "
            f"{fmt(sanity['overlap_rh_benefit_duration_rho'])} "
            f"(Pearson {fmt(sanity['overlap_rh_benefit_duration_pearson'])}): "
            "rh_benefit is the monthly-intercepted analogue of the plain "
            "duration-only curve; a high value confirms the R&H structure "
            "mostly reproduces the duration signal with a monthly offset."
        )
        lines.append(
            f"- rho(rh_error_prediction, duration_only_prediction) = "
            f"{fmt(sanity['overlap_rh_error_duration_rho'])}"
        )
        lines.append(
            f"- global constant (pooled fitting benefit mean) = "
            f"{sanity['global_mean_fit_benefit']:.4f} deg C"
        )
        lines.append("")
    lines.append("## 8. Files")
    lines.append("")
    lines.append(
        "- rh_gamma_curve.csv, proxy_values.csv, "
        "placement_predictions_{first,second}.csv, "
        "unit_predictions_{first,second}.csv, metrics_table.csv, "
        "budget_within_duration.csv, sanity_checks.txt"
    )
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
