"""Leakage-aware descriptive analysis and event labeling."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd


ACF_LAGS = (1, 7, 30, 90, 365)
HYDRO_VARIABLES = ("T", "F", "L")


def _safe_correlation(left: np.ndarray, right: np.ndarray) -> tuple[float, int]:
    valid = np.isfinite(left) & np.isfinite(right)
    left = np.asarray(left[valid], dtype=float)
    right = np.asarray(right[valid], dtype=float)
    count = int(valid.sum())
    if count < 3 or np.std(left) == 0 or np.std(right) == 0:
        return 0.0, count
    value = float(np.corrcoef(left, right)[0, 1])
    return (value if np.isfinite(value) else 0.0), count


def _rank_correlation(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    if valid.sum() < 3:
        return 0.0
    left_rank = pd.Series(left[valid]).rank(method="average").to_numpy(float)
    right_rank = pd.Series(right[valid]).rank(method="average").to_numpy(float)
    return _safe_correlation(left_rank, right_rank)[0]


def _lagged_pair(
    source: np.ndarray, target: np.ndarray, lag_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Positive lag means source at t is paired with target at t + lag."""

    lag_days = int(lag_days)
    if abs(lag_days) >= len(source):
        return np.empty(0), np.empty(0)
    if lag_days > 0:
        return source[:-lag_days], target[lag_days:]
    if lag_days < 0:
        return source[-lag_days:], target[:lag_days]
    return source, target


def lagged_correlation(
    source: np.ndarray | pd.Series,
    target: np.ndarray | pd.Series,
    lag_days: int,
) -> float:
    """Pearson correlation where positive lag means the source leads target."""

    source_values = np.asarray(source, dtype=float)
    target_values = np.asarray(target, dtype=float)
    if source_values.shape != target_values.shape or source_values.ndim != 1:
        raise ValueError("source and target must be equally sized one-dimensional arrays")
    left, right = _lagged_pair(source_values, target_values, lag_days)
    return _safe_correlation(left, right)[0]


def _approved_long(long: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "station_id", "variable", "value", "quality_approved", "split"}
    missing = required - set(long.columns)
    if missing:
        raise KeyError(f"daily_long is missing columns: {sorted(missing)}")
    result = long.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["approved_value"] = result["value"].where(
        result["quality_approved"].fillna(False).astype(bool)
    )
    return result.sort_values(["station_id", "variable", "date"])


def describe_variables(long: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (station, variable), group in long.groupby(
        ["station_id", "variable"], sort=False, observed=True
    ):
        values = group["approved_value"].dropna().to_numpy(float)
        quantiles = np.quantile(values, [0.01, 0.10, 0.50, 0.90, 0.99])
        rows.append(
            {
                "station_id": station,
                "variable": variable,
                "start_date": group["date"].min().date().isoformat(),
                "end_date": group["date"].max().date().isoformat(),
                "total_days": len(group),
                "approved_count": len(values),
                "coverage": len(values) / len(group),
                "mean": float(values.mean()),
                "std": float(values.std(ddof=1)),
                "min": float(values.min()),
                "q01": float(quantiles[0]),
                "q10": float(quantiles[1]),
                "median": float(quantiles[2]),
                "q90": float(quantiles[3]),
                "q99": float(quantiles[4]),
                "max": float(values.max()),
            }
        )
    return pd.DataFrame(rows)


def _value_columns(
    wide: pd.DataFrame, stations: list[str], variables: list[str]
) -> list[str]:
    return [
        f"{station}_{variable}"
        for station in stations
        for variable in variables
        if f"{station}_{variable}" in wide
    ]


def training_seasonal_anomalies(
    wide: pd.DataFrame, columns: list[str]
) -> pd.DataFrame:
    """Subtract month-day medians fitted only on the training split."""

    keys = pd.to_datetime(wide["date"]).dt.strftime("%m-%d")
    train = wide["split"].astype(str).eq("train")
    result = pd.DataFrame(index=wide.index)
    for column in columns:
        values = pd.to_numeric(wide[column], errors="coerce")
        climatology = values[train].groupby(keys[train]).median()
        fallback = float(values[train].median())
        expected = keys.map(climatology).fillna(fallback)
        result[column] = values - expected.to_numpy(float)
    return result


def daily_change_outputs(
    wide: pd.DataFrame, columns: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = wide["split"].astype(str).eq("train")
    summary_rows: list[dict[str, Any]] = []
    candidates: list[pd.DataFrame] = []
    for column in columns:
        station, variable = column.split("_", 1)
        values = pd.to_numeric(wide[column], errors="coerce")
        change = values.diff()
        train_change = change.where(train & train.shift(fill_value=False)).dropna()
        threshold = float(train_change.abs().quantile(0.99))
        selected = change.abs().gt(threshold) & change.notna()
        summary_rows.append(
            {
                "station_id": station,
                "variable": variable,
                "mean_change": float(change.mean()),
                "std_change": float(change.std()),
                "mean_absolute_change": float(change.abs().mean()),
                "q90_absolute_change": float(change.abs().quantile(0.90)),
                "q99_absolute_change": float(change.abs().quantile(0.99)),
                "max_absolute_change": float(change.abs().max()),
                "train_q99_step_threshold": threshold,
                "step_candidate_count": int(selected.sum()),
            }
        )
        if selected.any():
            candidates.append(
                pd.DataFrame(
                    {
                        "date": wide.loc[selected, "date"].to_numpy(),
                        "station_id": station,
                        "variable": variable,
                        "split": wide.loc[selected, "split"].to_numpy(),
                        "daily_change": change[selected].to_numpy(float),
                        "absolute_change": change[selected].abs().to_numpy(float),
                        "train_q99_threshold": threshold,
                        "candidate_only_not_removed": True,
                    }
                )
            )
    candidate_frame = (
        pd.concat(candidates, ignore_index=True)
        if candidates
        else pd.DataFrame(
            columns=[
                "date",
                "station_id",
                "variable",
                "split",
                "daily_change",
                "absolute_change",
                "train_q99_threshold",
                "candidate_only_not_removed",
            ]
        )
    )
    candidate_summary = (
        candidate_frame.groupby(["station_id", "variable", "split"], observed=True)
        .agg(candidate_count=("date", "size"), max_absolute_change=("absolute_change", "max"))
        .reset_index()
    )
    return pd.DataFrame(summary_rows), candidate_frame, candidate_summary


def seasonal_anomaly_summary(
    wide: pd.DataFrame,
    anomalies: pd.DataFrame,
    stations: list[str],
    variables: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seasons = wide["season"] if "season" in wide else pd.to_datetime(wide["date"]).dt.month
    for column in _value_columns(wide, stations, variables):
        station, variable = column.split("_", 1)
        for season, indices in seasons.groupby(seasons, observed=True).groups.items():
            values = anomalies.loc[indices, column].dropna().to_numpy(float)
            rows.append(
                {
                    "station_id": station,
                    "variable": variable,
                    "season": season,
                    "count": len(values),
                    "mean_anomaly": float(values.mean()),
                    "std_anomaly": float(values.std(ddof=1)),
                    "q10_anomaly": float(np.quantile(values, 0.10)),
                    "q90_anomaly": float(np.quantile(values, 0.90)),
                    "max_absolute_anomaly": float(np.abs(values).max()),
                }
            )
    return pd.DataFrame(rows)


def acf_table(
    wide: pd.DataFrame,
    anomalies: pd.DataFrame,
    stations: list[str],
    variables: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in _value_columns(wide, stations, variables):
        station, variable = column.split("_", 1)
        for series_name, series in (
            ("raw", pd.to_numeric(wide[column], errors="coerce")),
            ("seasonal_anomaly", anomalies[column]),
        ):
            values = series.to_numpy(float)
            for lag in ACF_LAGS:
                left, right = _lagged_pair(values, values, lag)
                correlation, count = _safe_correlation(left, right)
                rows.append(
                    {
                        "station_id": station,
                        "variable": variable,
                        "series": series_name,
                        "lag_days": lag,
                        "correlation": correlation,
                        "n_pairs": count,
                    }
                )
    return pd.DataFrame(rows)


def within_station_correlations(
    wide: pd.DataFrame,
    anomalies: pd.DataFrame,
    stations: list[str],
    variables: list[str],
) -> pd.DataFrame:
    train = wide["split"].astype(str).eq("train")
    rows: list[dict[str, Any]] = []
    for station in stations:
        available = [variable for variable in variables if f"{station}_{variable}" in wide]
        for left_variable, right_variable in combinations(available, 2):
            left_column = f"{station}_{left_variable}"
            right_column = f"{station}_{right_variable}"
            for series_name, frame in (("raw", wide), ("seasonal_anomaly", anomalies)):
                left = pd.to_numeric(frame.loc[train, left_column], errors="coerce").to_numpy(float)
                right = pd.to_numeric(frame.loc[train, right_column], errors="coerce").to_numpy(float)
                pearson, count = _safe_correlation(left, right)
                rows.append(
                    {
                        "station_id": station,
                        "variable_x": left_variable,
                        "variable_y": right_variable,
                        "series": series_name,
                        "period": "train",
                        "pearson": pearson,
                        "spearman": _rank_correlation(left, right),
                        "n_pairs": count,
                    }
                )
    return pd.DataFrame(rows)


def cross_station_lag_correlations(
    wide: pd.DataFrame,
    anomalies: pd.DataFrame,
    stations: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = wide["split"].astype(str).eq("train")
    rows: list[dict[str, Any]] = []
    for source, target in combinations(stations, 2):
        for variable in HYDRO_VARIABLES:
            source_column = f"{source}_{variable}"
            target_column = f"{target}_{variable}"
            if source_column not in wide or target_column not in wide:
                continue
            raw_source = pd.to_numeric(wide.loc[train, source_column], errors="coerce").to_numpy(float)
            raw_target = pd.to_numeric(wide.loc[train, target_column], errors="coerce").to_numpy(float)
            anomaly_source = anomalies.loc[train, source_column].to_numpy(float)
            anomaly_target = anomalies.loc[train, target_column].to_numpy(float)
            for lag in range(-30, 31):
                raw_left, raw_right = _lagged_pair(raw_source, raw_target, lag)
                anomaly_left, anomaly_right = _lagged_pair(
                    anomaly_source, anomaly_target, lag
                )
                raw_correlation, raw_count = _safe_correlation(raw_left, raw_right)
                anomaly_correlation, anomaly_count = _safe_correlation(
                    anomaly_left, anomaly_right
                )
                rows.append(
                    {
                        "source_station": source,
                        "target_station": target,
                        "variable": variable,
                        "lag_days": lag,
                        "lag_definition": "positive=source_leads_target",
                        "period": "train",
                        "raw_correlation": raw_correlation,
                        "raw_n_pairs": raw_count,
                        "anomaly_correlation": anomaly_correlation,
                        "anomaly_n_pairs": anomaly_count,
                    }
                )
    lag_table = pd.DataFrame(rows)
    best_rows: list[pd.Series] = []
    for _, group in lag_table.groupby(
        ["source_station", "target_station", "variable"], observed=True
    ):
        for series in ("raw", "anomaly"):
            correlation_column = f"{series}_correlation"
            selected = group.loc[group[correlation_column].abs().idxmax()].copy()
            selected["selected_series"] = series
            selected["selected_correlation"] = selected[correlation_column]
            best_rows.append(selected)
    return lag_table, pd.DataFrame(best_rows).reset_index(drop=True)


def build_event_labels(
    wide: pd.DataFrame, stations: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit station thresholds on train only, then label every date."""

    train = wide["split"].astype(str).eq("train")
    label_parts: list[pd.DataFrame] = []
    thresholds: list[dict[str, float | str | int]] = []
    for station in stations:
        temperature = pd.to_numeric(wide[f"{station}_T"], errors="coerce")
        flow = pd.to_numeric(wide[f"{station}_F"], errors="coerce")
        t90 = float(temperature[train].quantile(0.90))
        f90 = float(flow[train].quantile(0.90))
        f10 = float(flow[train].quantile(0.10))
        if not np.isfinite([t90, f90, f10]).all():
            raise ValueError(f"station {station} lacks finite train-only event thresholds")
        high_temperature = temperature.ge(t90) & temperature.notna()
        run_group = (~high_temperature).cumsum()
        heatwave = high_temperature & high_temperature.groupby(run_group).transform("sum").ge(3)
        label_parts.append(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(wide["date"]),
                    "station_id": station,
                    "split": wide["split"].astype(str),
                    "T": temperature,
                    "F": flow,
                    "T_q90_train": t90,
                    "F_q90_train": f90,
                    "F_q10_train": f10,
                    "high_temperature": high_temperature,
                    "heatwave_min_3d": heatwave,
                    "high_flow": flow.ge(f90) & flow.notna(),
                    "low_flow": flow.le(f10) & flow.notna(),
                }
            )
        )
        thresholds.append(
            {
                "station_id": station,
                "train_count_T": int(temperature[train].notna().sum()),
                "train_count_F": int(flow[train].notna().sum()),
                "T_q90_train": t90,
                "F_q90_train": f90,
                "F_q10_train": f10,
            }
        )
    return pd.concat(label_parts, ignore_index=True), pd.DataFrame(thresholds)


def _polynomial_r2(x: np.ndarray, y: np.ndarray, degree: int) -> float:
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) <= degree or np.var(y) == 0:
        return 0.0
    centered = x - x.mean()
    design = np.column_stack([centered**power for power in range(degree + 1)])
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = np.square(y - design @ coefficients).sum()
    total = np.square(y - y.mean()).sum()
    value = 1.0 - residual / total
    return float(value) if np.isfinite(value) else 0.0


def rating_curve_diagnostics(wide: pd.DataFrame, stations: list[str]) -> pd.DataFrame:
    years = pd.to_datetime(wide["date"]).dt.year
    rows: list[dict[str, Any]] = []
    for station in stations:
        for year, indices in years.groupby(years, observed=True).groups.items():
            level = pd.to_numeric(wide.loc[indices, f"{station}_L"], errors="coerce").to_numpy(float)
            flow = pd.to_numeric(wide.loc[indices, f"{station}_F"], errors="coerce").to_numpy(float)
            pearson, count = _safe_correlation(level, flow)
            rows.append(
                {
                    "station_id": station,
                    "year": int(year),
                    "n_pairs": count,
                    "pearson": pearson,
                    "spearman": _rank_correlation(level, flow),
                    "linear_r2": _polynomial_r2(level, flow, 1),
                    "quadratic_r2": _polynomial_r2(level, flow, 2),
                }
            )
    return pd.DataFrame(rows)


def _save_timeseries_and_seasonality(
    wide: pd.DataFrame,
    stations: list[str],
    variables: list[str],
    figure_root: Path,
) -> None:
    timeseries_dir = figure_root / "timeseries"
    seasonality_dir = figure_root / "seasonality"
    timeseries_dir.mkdir(parents=True, exist_ok=True)
    seasonality_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.to_datetime(wide["date"])
    day_of_year = dates.dt.dayofyear
    for variable in variables:
        fig, axis = plt.subplots(figsize=(11, 3.5))
        for station in stations:
            column = f"{station}_{variable}"
            if column in wide:
                axis.plot(dates, wide[column], linewidth=0.55, label=station)
        axis.set(title=f"{variable}: full daily record", xlabel="Date", ylabel=variable)
        axis.legend(ncol=len(stations), frameon=False)
        fig.tight_layout()
        fig.savefig(timeseries_dir / f"{variable}.png", dpi=150)
        plt.close(fig)

        fig, axis = plt.subplots(figsize=(8, 3.5))
        for station in stations:
            column = f"{station}_{variable}"
            if column in wide:
                seasonal = pd.to_numeric(wide[column], errors="coerce").groupby(day_of_year).median()
                axis.plot(seasonal.index, seasonal.values, linewidth=1.2, label=station)
        axis.set(
            title=f"{variable}: median seasonal cycle",
            xlabel="Day of year",
            ylabel=variable,
            xlim=(1, 366),
        )
        axis.legend(ncol=len(stations), frameon=False)
        fig.tight_layout()
        fig.savefig(seasonality_dir / f"{variable}.png", dpi=150)
        plt.close(fig)


def _save_availability(long: pd.DataFrame, figure_root: Path) -> None:
    approved = long["approved_value"].notna()
    annual = (
        approved.groupby(
            [long["station_id"], long["variable"], long["date"].dt.year], observed=True
        )
        .mean()
        .unstack(fill_value=0.0)
    )
    fig, axis = plt.subplots(figsize=(11, max(4, len(annual) * 0.24)))
    image = axis.imshow(annual.to_numpy(float), aspect="auto", vmin=0, vmax=1, cmap="viridis")
    axis.set_xticks(range(len(annual.columns)), annual.columns, rotation=45)
    axis.set_yticks(
        range(len(annual.index)),
        [f"{station}-{variable}" for station, variable in annual.index],
    )
    axis.set(title="Annual quality-approved coverage", xlabel="Year")
    fig.colorbar(image, ax=axis, label="Coverage")
    fig.tight_layout()
    figure_root.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_root / "availability.png", dpi=150)
    plt.close(fig)


def _save_rating_figures(
    wide: pd.DataFrame,
    stations: list[str],
    diagnostics: pd.DataFrame,
    qc_root: Path,
) -> None:
    qc_root.mkdir(parents=True, exist_ok=True)
    years = pd.to_datetime(wide["date"]).dt.year.to_numpy()
    for station in stations:
        level = pd.to_numeric(wide[f"{station}_L"], errors="coerce").to_numpy(float)
        flow = pd.to_numeric(wide[f"{station}_F"], errors="coerce").to_numpy(float)
        valid = np.isfinite(level) & np.isfinite(flow)
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        scatter = axes[0].scatter(
            level[valid], flow[valid], c=years[valid], s=5, alpha=0.45, cmap="viridis"
        )
        centered = level[valid] - level[valid].mean()
        design = np.column_stack([np.ones(valid.sum()), centered, centered**2])
        coefficients = np.linalg.lstsq(design, flow[valid], rcond=None)[0]
        grid = np.linspace(level[valid].min(), level[valid].max(), 250)
        grid_centered = grid - level[valid].mean()
        axes[0].plot(
            grid,
            coefficients[0] + coefficients[1] * grid_centered + coefficients[2] * grid_centered**2,
            color="black",
            linewidth=1.5,
            label="overall quadratic fit",
        )
        axes[0].set(title=f"{station}: F-L by year", xlabel="Water level L", ylabel="Flow F")
        axes[0].legend(frameon=False)
        fig.colorbar(scatter, ax=axes[0], label="Year")
        station_diagnostics = diagnostics[diagnostics["station_id"] == station]
        axes[1].plot(
            station_diagnostics["year"],
            station_diagnostics["linear_r2"],
            marker="o",
            label="linear R²",
        )
        axes[1].plot(
            station_diagnostics["year"],
            station_diagnostics["quadratic_r2"],
            marker="o",
            label="quadratic R²",
        )
        axes[1].set(title="Yearly fit diagnostics", xlabel="Year", ylabel="R²", ylim=(0, 1.02))
        axes[1].legend(frameon=False)
        fig.tight_layout()
        fig.savefig(qc_root / f"rating_curve_by_year_{station}.png", dpi=160)
        plt.close(fig)


def _study_area_points(
    station_metadata: pd.DataFrame, candidate_metadata: pd.DataFrame
) -> pd.DataFrame:
    core = station_metadata.copy()
    core["point_type"] = "core"
    core["coordinate_status"] = "station_metadata"
    core["plot_order"] = core["station_id"].map({"B1": 4, "S2": 8, "P3": 12})
    core["plot_order"] = core["plot_order"].fillna(
        pd.to_numeric(core["network_order"], errors="coerce") * 2 + 4
    )
    points = [
        core[["station_id", "station_name", "latitude", "longitude", "point_type", "coordinate_status", "plot_order"]]
    ]
    core_coordinates = core.set_index("station_id")[["latitude", "longitude"]].astype(float)
    order = {"ZMD": 0, "GT": 2, "BZL": 7, "JAQ": 10, "SDZ": 14}
    candidates: list[dict[str, Any]] = []
    for index, row in candidate_metadata.iterrows():
        station_id = str(row["station_id"])
        latitude = pd.to_numeric(pd.Series([row.get("latitude")]), errors="coerce").iloc[0]
        longitude = pd.to_numeric(pd.Series([row.get("longitude")]), errors="coerce").iloc[0]
        reason = str(row.get("selection_reason", ""))
        status = "metadata_proxy" if "proxy" in reason.lower() else "candidate_metadata"
        if not np.isfinite(latitude) or not np.isfinite(longitude):
            if station_id == "JAQ":
                latitude, longitude = core_coordinates.loc[["S2", "P3"]].mean().to_numpy()
            elif station_id == "SDZ":
                p3 = core_coordinates.loc["P3"].to_numpy()
                s2 = core_coordinates.loc["S2"].to_numpy()
                latitude, longitude = p3 + 0.30 * (p3 - s2)
            else:
                latitude, longitude = core_coordinates.mean().to_numpy() + np.array([0.15 * index, 0.15 * index])
            status = "plot_proxy_missing_metadata_coordinate"
        candidates.append(
            {
                "station_id": station_id,
                "station_name": row.get("station_name", station_id),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "point_type": "candidate",
                "coordinate_status": status,
                "plot_order": order.get(station_id, 20 + index),
            }
        )
    if candidates:
        points.append(pd.DataFrame(candidates))
    return pd.concat(points, ignore_index=True).sort_values("plot_order")


def _save_study_area(points: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(7.5, 7))
    ordered = points.sort_values("plot_order")
    axis.plot(ordered["longitude"], ordered["latitude"], color="#77aadd", linewidth=1.2, alpha=0.65)
    core = points[points["point_type"] == "core"]
    reported = points[
        (points["point_type"] == "candidate")
        & ~points["coordinate_status"].str.contains("proxy")
    ]
    proxy = points[points["coordinate_status"].str.contains("proxy")]
    axis.scatter(core["longitude"], core["latitude"], s=65, color="#114477", label="core station", zorder=3)
    if len(reported):
        axis.scatter(
            reported["longitude"],
            reported["latitude"],
            s=55,
            marker="^",
            facecolors="none",
            edgecolors="#228833",
            label="candidate coordinate",
            zorder=3,
        )
    if len(proxy):
        axis.scatter(
            proxy["longitude"],
            proxy["latitude"],
            s=60,
            marker="x",
            color="#cc3311",
            label="proxy coordinate",
            zorder=4,
        )
    for row in points.itertuples(index=False):
        suffix = "*" if "proxy" in row.coordinate_status else ""
        axis.annotate(f"{row.station_id}{suffix}", (row.longitude, row.latitude), xytext=(4, 3), textcoords="offset points")
    axis.set(
        title="Schematic Jinsha River station locations\n(no external basemap; * denotes proxy coordinates)",
        xlabel="Longitude",
        ylabel="Latitude",
    )
    axis.legend(frameon=False)
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def run_eda(
    long_path: str | Path,
    wide_path: str | Path,
    station_metadata_path: str | Path,
    candidate_metadata_path: str | Path,
    *,
    results_dir: str | Path,
    eda_figures_dir: str | Path,
    qc_figures_dir: str | Path,
    event_output: str | Path,
    study_area_output: str | Path,
) -> dict[str, Path]:
    """Run the complete local EDA/event-label batch and return written paths."""

    long = _approved_long(pd.read_parquet(long_path))
    wide = pd.read_parquet(wide_path).sort_values("date").reset_index(drop=True)
    wide["date"] = pd.to_datetime(wide["date"]).dt.normalize()
    stations_metadata = pd.read_csv(station_metadata_path).sort_values("network_order")
    candidates_metadata = pd.read_csv(candidate_metadata_path)
    stations = stations_metadata["station_id"].astype(str).tolist()
    variables = long["variable"].drop_duplicates().astype(str).tolist()
    columns = _value_columns(wide, stations, variables)
    if not {f"{station}_{variable}" for station in stations for variable in HYDRO_VARIABLES}.issubset(wide.columns):
        raise KeyError("daily_wide must contain T/F/L for every core station")

    results = Path(results_dir)
    eda_figures = Path(eda_figures_dir)
    qc_figures = Path(qc_figures_dir)
    results.mkdir(parents=True, exist_ok=True)
    anomalies = training_seasonal_anomalies(wide, columns)
    variable_summary = describe_variables(long)
    changes, step_candidates, step_summary = daily_change_outputs(wide, columns)
    anomaly_summary = seasonal_anomaly_summary(wide, anomalies, stations, variables)
    acf = acf_table(wide, anomalies, stations, variables)
    within = within_station_correlations(wide, anomalies, stations, variables)
    lag_table, best_lags = cross_station_lag_correlations(wide, anomalies, stations)
    events, event_thresholds = build_event_labels(wide, stations)
    rating = rating_curve_diagnostics(wide, stations)
    study_points = _study_area_points(stations_metadata, candidates_metadata)

    outputs = {
        "variable_summary": results / "variable_summary.csv",
        "daily_change_summary": results / "daily_change_summary.csv",
        "seasonal_anomaly_summary": results / "seasonal_anomaly_summary.csv",
        "step_candidates": results / "step_candidates.csv",
        "step_candidate_summary": results / "step_candidate_summary.csv",
        "acf": results / "acf.csv",
        "within_station_correlations": results / "within_station_correlations.csv",
        "cross_station_lag_correlations": results / "cross_station_lag_correlations.csv",
        "best_lags": results / "best_lag_summary.csv",
        "event_thresholds": results / "event_thresholds.csv",
        "rating_curve_diagnostics": results / "rating_curve_diagnostics.csv",
        "study_area_points": results / "study_area_points.csv",
        "report": results / "information_structure_report.md",
        "event_labels": Path(event_output),
        "study_area": Path(study_area_output),
    }
    for frame, key in (
        (variable_summary, "variable_summary"),
        (changes, "daily_change_summary"),
        (anomaly_summary, "seasonal_anomaly_summary"),
        (step_candidates, "step_candidates"),
        (step_summary, "step_candidate_summary"),
        (acf, "acf"),
        (within, "within_station_correlations"),
        (lag_table, "cross_station_lag_correlations"),
        (best_lags, "best_lags"),
        (event_thresholds, "event_thresholds"),
        (rating, "rating_curve_diagnostics"),
        (study_points, "study_area_points"),
    ):
        frame.to_csv(outputs[key], index=False)
    outputs["event_labels"].parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(outputs["event_labels"], index=False)

    _save_timeseries_and_seasonality(wide, stations, variables, eda_figures)
    _save_availability(long, eda_figures)
    _save_rating_figures(wide, stations, rating, qc_figures)
    _save_study_area(study_points, outputs["study_area"])

    november_2018 = long[long["date"].between("2018-11-01", "2018-11-30")]
    report_lines = [
        "# Information structure report",
        "",
        "All thresholds and lag selection diagnostics use the training split only.",
        "Step candidates are flagged for review and are not removed.",
        f"November 2018 is retained: {len(november_2018)} long-format rows, "
        f"{int(november_2018['approved_value'].notna().sum())} quality-approved values.",
        "",
        "## Train-only event thresholds",
        "",
        "```text",
        event_thresholds.to_string(index=False),
        "```",
        "",
        "## Strongest train-only cross-station lags",
        "",
        "```text",
        best_lags[
            [
                "source_station",
                "target_station",
                "variable",
                "selected_series",
                "lag_days",
                "selected_correlation",
            ]
        ].to_string(index=False),
        "```",
        "",
        "Positive lag means the source station leads the target station.",
    ]
    outputs["report"].write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return outputs
