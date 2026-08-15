"""Reproducible publication figures, tables, and a result-freeze manifest.

The builders in this module only summarize existing result files.  They do not
run models or synthesize missing scientific results.  When an input needed by a
figure or table is unavailable, the artifact is omitted and the reason is
recorded in the manifests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
import numpy as np
import pandas as pd


LOSO_TITLE = "Exploratory internal leave-one-station-out (not external validation)"
SOURCE_LABELS = {
    "A": "A: local temporal",
    "B": "B: same-site hydro",
    "C": "C: cross-station",
    "D": "D: meteorology/season",
}
MODEL_ORDER = (
    "climatology",
    "linear",
    "pchip",
    "kalman",
    "air_only",
    "air_hydro",
    "donor_regression",
    "random_forest",
    "xgboost",
    "brits",
    "saits",
    "proposed",
    "pooled_loso",
)
MODEL_COLORS = {
    model: plt.get_cmap("tab20")(index / max(1, len(MODEL_ORDER) - 1))
    for index, model in enumerate(MODEL_ORDER)
}


class ArtifactUnavailable(ValueError):
    """Expected absence or insufficiency of a publication input."""


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported table format: {path}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def _write_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(dict(value)), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _save_figure(figure: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "stream-recoverability"},
    )
    plt.close(figure)


def _write_table(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _require_frame(
    frame: pd.DataFrame | None,
    columns: Iterable[str],
    context: str,
) -> pd.DataFrame:
    if frame is None:
        raise ArtifactUnavailable(f"{context} input is missing")
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ArtifactUnavailable(f"{context} is missing columns: {missing}")
    if frame.empty:
        raise ArtifactUnavailable(f"{context} has no rows")
    return frame


def _ordered_models(values: Iterable[object]) -> list[str]:
    present = {str(value) for value in values if pd.notna(value)}
    ordered = [model for model in MODEL_ORDER if model in present]
    return [*ordered, *sorted(present.difference(ordered))]


def _infer_mask_type(scenario_id: object, experiment: object = None) -> str | None:
    scenario = str(scenario_id).upper()
    exp = "" if pd.isna(experiment) else str(experiment).upper()
    if exp == "M1" or scenario.startswith(("M1-", "PNT-")):
        return "point"
    if exp == "M2" or scenario.startswith(("M2-", "BLK-")):
        return "block"
    if exp == "M3" or scenario.startswith(("M3-", "MBLK-")):
        return "multiblock"
    if exp == "M4" or "SITE" in scenario:
        return "station_outage"
    if exp == "M6":
        return "async" if "ASYNC" in scenario else "network_outage"
    if exp == "M7" or "EVENT" in scenario:
        return "event"
    if exp == "M10" or "LOSO" in scenario:
        return "loso"
    return None


def _infer_experiment(scenario_id: object, mask_type: object = None) -> str | None:
    scenario = str(scenario_id).upper()
    for value in range(1, 11):
        if scenario.startswith(f"M{value}-"):
            return f"M{value}"
    kind = "" if pd.isna(mask_type) else str(mask_type)
    return {"point": "M1", "block": "M2", "multiblock": "M3"}.get(kind)


def _infer_event_type(scenario_id: object) -> str | None:
    scenario = str(scenario_id).upper().replace("-", "_")
    if "HIGH_TEMPERATURE" in scenario or "HIGHTEMP" in scenario:
        return "high_temperature"
    if "LOW_FLOW" in scenario or "LOWFLOW" in scenario:
        return "low_flow"
    if "FLOOD" in scenario or "HIGH_FLOW" in scenario:
        return "flood"
    return None


def _enrich_results(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None:
        return None
    data = frame.copy()
    if "scenario_id" not in data:
        return data
    if "experiment" not in data:
        data["experiment"] = None
    if "mask_type" not in data:
        data["mask_type"] = None
    missing_mask = data["mask_type"].isna()
    data.loc[missing_mask, "mask_type"] = [
        _infer_mask_type(scenario, experiment)
        for scenario, experiment in data.loc[missing_mask, ["scenario_id", "experiment"]].itertuples(index=False, name=None)
    ]
    missing_experiment = data["experiment"].isna()
    data.loc[missing_experiment, "experiment"] = [
        _infer_experiment(scenario, mask_type)
        for scenario, mask_type in data.loc[missing_experiment, ["scenario_id", "mask_type"]].itertuples(index=False, name=None)
    ]
    if "event_type" not in data:
        data["event_type"] = None
    missing_event = data["event_type"].isna()
    data.loc[missing_event, "event_type"] = data.loc[missing_event, "scenario_id"].map(
        _infer_event_type
    )
    return data


def _frame_summary(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None:
        return {"rows": 0, "columns": [], "models": [], "scenario_count": 0, "scenario_summary": []}
    models = _ordered_models(frame["model"].dropna()) if "model" in frame else []
    scenario_count = int(frame["scenario_id"].nunique()) if "scenario_id" in frame else 0
    group_columns = [
        column for column in ("experiment", "mask_type", "target") if column in frame
    ]
    if group_columns and "scenario_id" in frame:
        grouped = (
            frame.groupby(group_columns, dropna=False, observed=True)
            .agg(rows=("scenario_id", "size"), scenarios=("scenario_id", "nunique"))
            .reset_index()
        )
        scenario_summary = grouped.to_dict("records")
    else:
        scenario_summary = []
    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "models": models,
        "scenario_count": scenario_count,
        "scenario_summary": scenario_summary,
    }


def _load_optional_table(path: Path, inputs: dict[str, Any], name: str) -> pd.DataFrame | None:
    entry: dict[str, Any] = {"path": str(path)}
    if not path.exists():
        entry.update({"status": "missing", "rows": 0, "columns": []})
        inputs[name] = entry
        return None
    try:
        frame = _read_table(path)
    except (OSError, ValueError) as error:
        entry.update({"status": "unreadable", "reason": str(error), "rows": 0, "columns": []})
        inputs[name] = entry
        return None
    entry.update(
        {
            "status": "available",
            "rows": int(len(frame)),
            "columns": [str(column) for column in frame.columns],
        }
    )
    inputs[name] = entry
    return frame


def _artifact_status(
    path: Path,
    title: str,
    status: str,
    *,
    reason: str | None = None,
    source_rows: int | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "path": str(path),
        "title": title,
        "reason": reason,
        "source_rows": source_rows,
        "details": dict(details or {}),
    }


def _figure_01(
    path: Path,
    station_metadata: pd.DataFrame | None,
    variable_summary: pd.DataFrame | None,
    study_points: pd.DataFrame | None,
    availability_image: Path,
) -> dict[str, Any]:
    stations = _require_frame(
        station_metadata,
        ("station_id", "latitude", "longitude"),
        "station metadata",
    ).copy()
    summary = _require_frame(
        variable_summary,
        ("station_id", "variable", "coverage"),
        "EDA variable summary",
    ).copy()
    for column in ("latitude", "longitude"):
        stations[column] = pd.to_numeric(stations[column], errors="coerce")
    stations = stations.dropna(subset=["latitude", "longitude"])
    if stations.empty:
        raise ArtifactUnavailable("station metadata has no finite coordinates")

    points = study_points.copy() if study_points is not None and not study_points.empty else stations.copy()
    for column in ("latitude", "longitude"):
        points[column] = pd.to_numeric(points[column], errors="coerce")
    points = points.dropna(subset=["latitude", "longitude"])
    if "plot_order" in points:
        points = points.sort_values("plot_order")
    elif "network_order" in points:
        points = points.sort_values("network_order")

    figure, axes = plt.subplots(1, 2, figsize=(12.2, 5.1), constrained_layout=True)
    axis = axes[0]
    core = points.loc[points.get("point_type", pd.Series("core", index=points.index)).eq("core")]
    candidate = points.drop(core.index)
    if len(points) > 1:
        axis.plot(points["longitude"], points["latitude"], color="#6aaed6", linewidth=1.4, alpha=0.7)
    if len(candidate):
        axis.scatter(
            candidate["longitude"], candidate["latitude"], marker="^", s=45,
            facecolors="none", edgecolors="#4c956c", label="candidate/proxy site",
        )
    axis.scatter(core["longitude"], core["latitude"], s=62, color="#174a7e", label="core site", zorder=3)
    for row in points.itertuples(index=False):
        axis.annotate(str(row.station_id), (row.longitude, row.latitude), xytext=(4, 3), textcoords="offset points", fontsize=8)
    if len(core) > 1:
        ordered = core.sort_values("network_order") if "network_order" in core else core
        first, last = ordered.iloc[0], ordered.iloc[-1]
        axis.add_patch(
            FancyArrowPatch(
                (first["longitude"], first["latitude"]),
                (last["longitude"], last["latitude"]),
                arrowstyle="-|>", mutation_scale=12, color="#174a7e", linewidth=1.0,
                connectionstyle="arc3,rad=0.08",
            )
        )
        axis.text(0.04, 0.04, "upstream → downstream", transform=axis.transAxes, fontsize=8)
    met_required = {"met_longitude", "met_latitude"}
    if met_required.issubset(stations.columns):
        met = stations.copy()
        met["met_longitude"] = pd.to_numeric(met["met_longitude"], errors="coerce")
        met["met_latitude"] = pd.to_numeric(met["met_latitude"], errors="coerce")
        met = met.dropna(subset=["met_longitude", "met_latitude"])
        if len(met):
            axis.scatter(
                met["met_longitude"], met["met_latitude"], marker="x", s=45,
                color="#d1495b", label="meteorological site", zorder=4,
            )
    axis.set(
        title="(a) Jinsha River monitoring network",
        xlabel="Longitude (°E)",
        ylabel="Latitude (°N)",
    )
    axis.grid(alpha=0.2)
    axis.legend(frameon=False, fontsize=8, loc="best")

    if availability_image.exists():
        axes[1].imshow(plt.imread(availability_image))
        axes[1].axis("off")
        axes[1].set_title("(b) Annual quality-approved availability")
        availability_source = "EDA availability image"
    else:
        summary["coverage"] = pd.to_numeric(summary["coverage"], errors="coerce")
        pivot = summary.pivot_table(
            index="station_id", columns="variable", values="coverage", aggfunc="mean"
        )
        if pivot.empty or not np.isfinite(pivot.to_numpy(dtype=float)).any():
            plt.close(figure)
            raise ArtifactUnavailable("EDA variable summary has no finite coverage values")
        image = axes[1].imshow(pivot.to_numpy(dtype=float), aspect="auto", vmin=0, vmax=1, cmap="viridis")
        axes[1].set_xticks(range(len(pivot.columns)), pivot.columns, rotation=45, ha="right")
        axes[1].set_yticks(range(len(pivot.index)), pivot.index)
        axes[1].set_title("(b) Quality-approved variable coverage")
        axes[1].set_xlabel("Variable")
        figure.colorbar(image, ax=axes[1], label="Coverage", shrink=0.82)
        availability_source = "EDA variable summary"
    figure.suptitle("Study area, monitoring variables, and data availability", fontsize=13)
    _save_figure(figure, path)
    return {
        "stations": sorted(stations["station_id"].astype(str).unique()),
        "availability_source": availability_source,
    }


def _small_mask(kind: str) -> np.ndarray:
    mask = np.zeros((12, 6), dtype=float)
    if kind == "random point":
        mask[[1, 4, 7, 10], [0, 3, 1, 5]] = 1
    elif kind == "single block":
        mask[3:9, 0] = 1
    elif kind == "multiple blocks":
        mask[1:4, 0] = 1
        mask[7:11, 0] = 1
    elif kind == "single variable":
        mask[3:9, 0] = 1
    elif kind == "multivariable":
        mask[3:9, :3] = 1
    elif kind == "whole station":
        mask[3:9, :] = 1
    elif kind == "two-station":
        mask[2:8, :3] = 1
        mask[2:8, 3:] = 1
    elif kind == "asynchronous":
        mask[1:7, :3] = 1
        mask[5:11, 3:] = 1
    return mask


def _figure_02(path: Path) -> dict[str, Any]:
    patterns = (
        "random point", "single block", "multiple blocks", "single variable",
        "multivariable", "whole station", "two-station", "asynchronous",
    )
    figure = plt.figure(figsize=(12.2, 7.2), constrained_layout=True)
    grid = figure.add_gridspec(3, 4, height_ratios=(1.0, 1.0, 1.15))
    for index, label in enumerate(patterns):
        axis = figure.add_subplot(grid[index // 4, index % 4])
        axis.imshow(_small_mask(label).T, aspect="auto", cmap="Greys", vmin=0, vmax=1)
        axis.set_title(label, fontsize=9)
        axis.set_xticks([])
        axis.set_yticks([])
        axis.set_xlabel("time →", fontsize=8)
    axis = figure.add_subplot(grid[2, :])
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 2.3)
    axis.axis("off")
    source_x = (0.4, 3.0, 5.6, 8.2)
    source_colors = ("#4c78a8", "#f58518", "#54a24b", "#b279a2")
    for x, source, color in zip(source_x, ("A", "B", "C", "D"), source_colors, strict=True):
        box = FancyBboxPatch(
            (x, 1.25), 2.2, 0.62, boxstyle="round,pad=0.04",
            facecolor=color, edgecolor="none", alpha=0.86,
        )
        axis.add_patch(box)
        axis.text(x + 1.1, 1.56, SOURCE_LABELS[source], ha="center", va="center", color="white", fontsize=8)
        axis.add_patch(FancyArrowPatch((x + 1.1, 1.23), (6.0, 0.84), arrowstyle="->", mutation_scale=9, color=color))
    fusion = FancyBboxPatch(
        (4.55, 0.25), 2.9, 0.58, boxstyle="round,pad=0.05",
        facecolor="#e8eef5", edgecolor="#174a7e", linewidth=1.2,
    )
    axis.add_patch(fusion)
    axis.text(6.0, 0.54, "availability-gated reconstruction", ha="center", va="center", fontsize=9)
    axis.add_patch(FancyArrowPatch((7.48, 0.54), (9.2, 0.54), arrowstyle="-|>", mutation_scale=12, color="#174a7e"))
    axis.text(10.25, 0.54, "recovered series\n+ uncertainty", ha="center", va="center", fontsize=9)
    axis.text(0.0, 2.08, "(a) Artificial missingness scenarios", fontsize=10, weight="bold")
    axis.text(0.0, 1.02, "(b) Four observed information groups", fontsize=10, weight="bold")
    figure.suptitle("Missingness experiments and recoverability framework", fontsize=13)
    _save_figure(figure, path)
    return {"patterns": list(patterns), "information_sources": list(SOURCE_LABELS)}


def _condition_label(row: pd.Series) -> str:
    experiment = "" if pd.isna(row.get("experiment")) else str(row.get("experiment"))
    mask = "unknown" if pd.isna(row.get("mask_type")) else str(row.get("mask_type"))
    pattern = "" if pd.isna(row.get("pattern")) else str(row.get("pattern"))
    gap = pd.to_numeric(pd.Series([row.get("gap_length")]), errors="coerce").iloc[0]
    rate = pd.to_numeric(pd.Series([row.get("missing_rate")]), errors="coerce").iloc[0]
    if np.isfinite(rate):
        magnitude = f"{100 * rate:.0f}%"
    elif np.isfinite(gap):
        magnitude = f"{gap:.0f} d"
    else:
        magnitude = ""
    prefix = f"{experiment} " if experiment else ""
    return "\n".join(value for value in (f"{prefix}{mask}", magnitude, pattern) if value)


def _figure_03(path: Path, events: pd.DataFrame | None) -> dict[str, Any]:
    data = _require_frame(events, ("model", "target"), "event metrics").copy()
    data = data.loc[data["target"].astype(str).str.upper().eq("T")]
    if "experiment" in data and data["experiment"].notna().any():
        data = data.loc[data["experiment"].astype(str).isin(["M1", "M2", "M3", "M4"])]
    if "model_status" in data:
        data = data.loc[data["model_status"].fillna("ok").eq("ok")]
    metric = next(
        (
            column
            for column in ("skill", "NMAE")
            if column in data and pd.to_numeric(data[column], errors="coerce").notna().any()
        ),
        None,
    )
    if metric is None:
        raise ArtifactUnavailable("T event metrics contain neither finite skill nor NMAE")
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.dropna(subset=[metric, "model"])
    if data.empty:
        raise ArtifactUnavailable("no finite T model-comparison rows")
    data["condition"] = data.apply(_condition_label, axis=1)
    sort_columns = [
        column for column in ("experiment", "mask_type", "missing_rate", "gap_length", "pattern") if column in data
    ]
    conditions = data.sort_values(sort_columns, na_position="last")["condition"].drop_duplicates().tolist()
    models = _ordered_models(data["model"])
    matrix = data.pivot_table(index="model", columns="condition", values=metric, aggfunc="median")
    matrix = matrix.reindex(index=models, columns=conditions).dropna(axis=0, how="all").dropna(axis=1, how="all")
    if matrix.empty:
        raise ArtifactUnavailable("T model-comparison matrix is empty")
    values = matrix.to_numpy(dtype=float)
    figure, axis = plt.subplots(figsize=(max(9.0, 0.55 * len(matrix.columns) + 3.5), max(4.4, 0.4 * len(matrix.index) + 2.0)), constrained_layout=True)
    if metric == "skill":
        finite = np.abs(values[np.isfinite(values)])
        limit = max(0.5, min(2.0, float(np.quantile(finite, 0.95)))) if finite.size else 1.0
        image = axis.imshow(values, aspect="auto", cmap="RdYlBu", vmin=-limit, vmax=limit)
        color_label = "Median skill (vs climatology)"
    else:
        image = axis.imshow(values, aspect="auto", cmap="viridis_r")
        color_label = "Median NMAE (lower is better)"
    axis.set_xticks(range(len(matrix.columns)), matrix.columns, rotation=55, ha="right", fontsize=8)
    axis.set_yticks(range(len(matrix.index)), matrix.index)
    axis.set_xlabel("Missingness condition")
    axis.set_ylabel("Model")
    axis.set_title("Temperature recovery across core missingness conditions")
    if matrix.size <= 180:
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                value = values[row, column]
                if np.isfinite(value):
                    axis.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=6)
    figure.colorbar(image, ax=axis, label=color_label, shrink=0.86)
    _save_figure(figure, path)
    return {"metric": metric, "models": list(matrix.index), "conditions": list(matrix.columns)}


def _selected_frontier_models(data: pd.DataFrame) -> list[str]:
    present = _ordered_models(data["model"])
    preferred = [
        model for model in ("proposed", "linear", "kalman", "donor_regression", "random_forest", "xgboost")
        if model in present
    ]
    return (preferred or present)[:6]


def _figure_04(
    path: Path,
    skill_curves: pd.DataFrame | None,
    frontiers: pd.DataFrame | None,
) -> dict[str, Any]:
    data = _require_frame(
        skill_curves,
        ("gap_length", "mean_skill", "station_id", "target", "model"),
        "recoverability skill curves",
    ).copy()
    data = data.loc[data["target"].astype(str).str.upper().eq("T")]
    if "pattern" in data and data["pattern"].notna().any():
        direct = data["pattern"].astype(str).eq("T")
        if direct.any():
            data = data.loc[direct]
    data["gap_length"] = pd.to_numeric(data["gap_length"], errors="coerce")
    data["mean_skill"] = pd.to_numeric(data["mean_skill"], errors="coerce")
    data = data.dropna(subset=["gap_length", "mean_skill", "station_id", "model"])
    if data.empty or data["gap_length"].nunique() < 2:
        raise ArtifactUnavailable("frontier curves require at least two finite T gap lengths")
    models = _selected_frontier_models(data)
    data = data.loc[data["model"].astype(str).isin(models)]
    stations = sorted(data["station_id"].astype(str).unique())
    figure, axes = plt.subplots(1, len(stations), figsize=(4.4 * len(stations), 4.2), sharey=True, squeeze=False, constrained_layout=True)
    grouping = ["model"]
    info_col = next((column for column in ("information_combination", "available_information") if column in data), None)
    if info_col is not None:
        grouping.append(info_col)
    for index, station in enumerate(stations):
        axis = axes[0, index]
        selected = data.loc[data["station_id"].astype(str).eq(station)]
        for group_key, group in selected.groupby(grouping, dropna=False, observed=True):
            if not isinstance(group_key, tuple):
                group_key = (group_key,)
            model = str(group_key[0])
            label = model if len(group_key) == 1 else f"{model}: {group_key[1]}"
            curve = group.groupby("gap_length", as_index=False).agg(
                mean_skill=("mean_skill", "mean"),
                ci_lower=("ci_lower", "mean") if "ci_lower" in group else ("mean_skill", lambda _: np.nan),
                ci_upper=("ci_upper", "mean") if "ci_upper" in group else ("mean_skill", lambda _: np.nan),
            ).sort_values("gap_length")
            color = MODEL_COLORS.get(model, None)
            axis.plot(curve["gap_length"], curve["mean_skill"], marker="o", linewidth=1.5, markersize=3, label=label, color=color)
            lower = pd.to_numeric(curve["ci_lower"], errors="coerce").to_numpy(float)
            upper = pd.to_numeric(curve["ci_upper"], errors="coerce").to_numpy(float)
            finite = np.isfinite(lower) & np.isfinite(upper)
            if finite.any():
                gaps = curve["gap_length"].to_numpy(float)
                axis.fill_between(gaps, lower, upper, where=finite, alpha=0.15, color=color)
        if frontiers is not None and not frontiers.empty:
            subset = frontiers.loc[
                frontiers.get("station_id", pd.Series(index=frontiers.index, dtype=object)).astype(str).eq(station)
                & frontiers.get("target", pd.Series(index=frontiers.index, dtype=object)).astype(str).str.upper().eq("T")
            ]
            if "statistical_frontier_days" in subset:
                proposed = subset.loc[subset.get("model", pd.Series(index=subset.index, dtype=object)).astype(str).eq("proposed")]
                chosen = proposed if len(proposed) else subset
                finite_frontier = pd.to_numeric(chosen["statistical_frontier_days"], errors="coerce").dropna()
                if len(finite_frontier):
                    frontier = float(finite_frontier.iloc[0])
                    axis.axvline(frontier, linestyle=":", linewidth=1.0, color="black")
                    axis.text(frontier, 0.02, f"frontier {frontier:.0f} d", rotation=90, va="bottom", ha="right", fontsize=7)
        axis.axhline(0.0, color="black", linewidth=0.9, linestyle="--")
        axis.set_title(station)
        axis.set_xlabel("Gap length (days)")
        axis.grid(alpha=0.2)
    axes[0, 0].set_ylabel("Mean skill (vs climatology)")
    handles, labels = axes[0, -1].get_legend_handles_labels()
    if handles:
        axes[0, -1].legend(handles, labels, frameon=False, fontsize=7, loc="best")
    figure.suptitle("Temperature recoverability frontiers with 95% confidence intervals", fontsize=13)
    _save_figure(figure, path)
    return {"stations": stations, "models": models, "zero_skill_reference": True}


def _figure_05(path: Path, shapley: pd.DataFrame | None) -> dict[str, Any]:
    data = _require_frame(
        shapley,
        ("source", "shapley", "gap_length", "target"),
        "information Shapley results",
    ).copy()
    data = data.loc[data["target"].astype(str).str.upper().eq("T")]
    if "reason" in data:
        data = data.loc[data["reason"].isna()]
    if "model" in data and data["model"].notna().any():
        models = sorted(data["model"].dropna().astype(str).unique())
        if "proposed" in models:
            data = data.loc[data["model"].astype(str).eq("proposed")]
            selected_model = "proposed"
        elif len(models) == 1:
            selected_model = models[0]
        else:
            raise ArtifactUnavailable("Shapley rows contain multiple models but no proposed model")
    else:
        selected_model = None
    data["gap_length"] = pd.to_numeric(data["gap_length"], errors="coerce")
    data["shapley"] = pd.to_numeric(data["shapley"], errors="coerce")
    data = data.dropna(subset=["gap_length", "shapley", "source"])
    if data["gap_length"].nunique() < 2:
        raise ArtifactUnavailable("Shapley plot requires at least two finite gap lengths")
    available_sources = [source for source in SOURCE_LABELS if source in set(data["source"].astype(str))]
    if set(available_sources) != set(SOURCE_LABELS):
        raise ArtifactUnavailable("Shapley plot requires complete A/B/C/D contributions")
    if "station_id" in data and data["station_id"].notna().any():
        stations: list[str | None] = sorted(data["station_id"].dropna().astype(str).unique())
    else:
        stations = [None]
    figure, axes = plt.subplots(1, len(stations), figsize=(4.4 * len(stations), 4.2), sharey=True, squeeze=False, constrained_layout=True)
    colors = {"A": "#4c78a8", "B": "#f58518", "C": "#54a24b", "D": "#b279a2"}
    for index, station in enumerate(stations):
        axis = axes[0, index]
        selected = data if station is None else data.loc[data["station_id"].astype(str).eq(station)]
        pivot = selected.pivot_table(index="gap_length", columns="source", values="shapley", aggfunc="mean").sort_index()
        pivot = pivot.reindex(columns=available_sources)
        if pivot.isna().any().any():
            plt.close(figure)
            raise ArtifactUnavailable(f"incomplete A/B/C/D Shapley grid for station {station or 'pooled'}")
        gaps = pivot.index.to_numpy(float)
        values = pivot.to_numpy(float).T
        positive = np.maximum(values, 0.0)
        negative = np.minimum(values, 0.0)
        axis.stackplot(gaps, positive, labels=[SOURCE_LABELS[source] for source in available_sources], colors=[colors[source] for source in available_sources], alpha=0.85)
        if np.any(negative < 0):
            axis.stackplot(gaps, negative, colors=[colors[source] for source in available_sources], alpha=0.55)
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_title("Pooled" if station is None else station)
        axis.set_xlabel("Gap length (days)")
        axis.grid(alpha=0.18)
    axes[0, 0].set_ylabel("Shapley contribution to recovery value")
    axes[0, -1].legend(frameon=False, fontsize=7, loc="best")
    figure.suptitle("Information compensation across missing-gap duration", fontsize=13)
    _save_figure(figure, path)
    return {"stations": [station or "pooled" for station in stations], "model": selected_model, "sources": available_sources}


def _figure_06(
    path: Path,
    resilience: pd.DataFrame | None,
    node_importance: pd.DataFrame | None,
) -> dict[str, Any]:
    data = _require_frame(
        resilience,
        ("failure_fraction", "relative_skill", "model", "target"),
        "network resilience curve",
    ).copy()
    data = data.loc[data["target"].astype(str).str.upper().eq("T")]
    data["failure_fraction"] = pd.to_numeric(data["failure_fraction"], errors="coerce")
    data["relative_skill"] = pd.to_numeric(data["relative_skill"], errors="coerce")
    data = data.dropna(subset=["failure_fraction", "relative_skill", "model"])
    if data.empty or data["failure_fraction"].nunique() < 2:
        raise ArtifactUnavailable("network resilience requires at least two failure fractions")
    present_models = _ordered_models(data["model"])
    models = (["proposed"] if "proposed" in present_models else present_models[:5])
    data = data.loc[data["model"].astype(str).isin(models)]
    figure, axes = plt.subplots(1, 2, figsize=(10.6, 4.2), constrained_layout=True)
    grouping = ["model"] + (["gap_length"] if "gap_length" in data else [])
    for group_key, group in data.groupby(grouping, dropna=False, observed=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        model = str(group_key[0])
        label = model if len(group_key) == 1 else f"{model}, {group_key[1]:g} d"
        curve = group.groupby("failure_fraction", as_index=False)["relative_skill"].mean().sort_values("failure_fraction")
        axes[0].plot(curve["failure_fraction"], curve["relative_skill"], marker="o", label=label, color=MODEL_COLORS.get(model))
    axes[0].axhline(0.0, color="black", linestyle="--", linewidth=0.8)
    axes[0].set(
        title="(a) Remaining network recovery skill",
        xlabel="Failed-station fraction",
        ylabel="Relative skill",
        xlim=(-0.02, 1.02),
    )
    axes[0].grid(alpha=0.2)
    axes[0].legend(frameon=False, fontsize=7)

    importance_rows = 0
    if node_importance is not None and not node_importance.empty and {"station_id", "impact"}.issubset(node_importance):
        importance = node_importance.copy()
        if "target" in importance:
            importance = importance.loc[importance["target"].astype(str).str.upper().eq("T")]
        if "model" in importance:
            importance = importance.loc[importance["model"].astype(str).isin(models)]
        importance["impact"] = pd.to_numeric(importance["impact"], errors="coerce")
        grouped = importance.dropna(subset=["impact"]).groupby("station_id", as_index=False)["impact"].mean().sort_values("impact", ascending=False)
        importance_rows = len(grouped)
        if len(grouped):
            axes[1].bar(grouped["station_id"].astype(str), grouped["impact"], color="#d1495b")
            axes[1].set(title="(b) Singleton-failure node importance", xlabel="Failed station", ylabel="Skill impact")
            axes[1].grid(axis="y", alpha=0.2)
        else:
            axes[1].text(0.5, 0.5, "Node-importance rows unavailable", ha="center", va="center")
            axes[1].axis("off")
    else:
        axes[1].text(0.5, 0.5, "Node-importance analysis unavailable", ha="center", va="center")
        axes[1].axis("off")
    figure.suptitle("Monitoring-network resilience under station failures", fontsize=13)
    _save_figure(figure, path)
    return {"models": models, "node_importance_rows": importance_rows}


def _contiguous_spans(dates: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    unique = pd.Series(pd.to_datetime(dates).dropna().unique()).sort_values().reset_index(drop=True)
    if unique.empty:
        return []
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start = previous = pd.Timestamp(unique.iloc[0])
    for value in unique.iloc[1:]:
        current = pd.Timestamp(value)
        if current - previous > pd.Timedelta(days=1):
            spans.append((start, previous))
            start = current
        previous = current
    spans.append((start, previous))
    return spans


def _select_event_case(data: pd.DataFrame, event_type: str, target: str) -> tuple[pd.DataFrame, str]:
    candidates = data.loc[
        data["event_type"].astype(str).eq(event_type)
        & data["target"].astype(str).str.upper().eq(target)
    ]
    if candidates.empty:
        raise ArtifactUnavailable(f"no real {event_type} {target} prediction rows")
    grouping = ["scenario_id"] + (["station_id"] if "station_id" in candidates else [])
    options: list[tuple[int, str, pd.DataFrame, str]] = []
    for keys, group in candidates.groupby(grouping, dropna=False, observed=True):
        models = set(group["model"].dropna().astype(str))
        required = {"linear", "proposed"}
        alternatives = sorted(models - required)
        if not required.issubset(models) or not alternatives:
            continue
        proposed = group.loc[group["model"].astype(str).eq("proposed")]
        if not {"q05", "q95"}.issubset(proposed) or not proposed[["q05", "q95"]].apply(pd.to_numeric, errors="coerce").notna().all(axis=1).any():
            continue
        errors = []
        for model in alternatives:
            selected = group.loc[group["model"].astype(str).eq(model)]
            truth = pd.to_numeric(selected["y_true"], errors="coerce")
            prediction = pd.to_numeric(selected["y_pred"], errors="coerce")
            valid = truth.notna() & prediction.notna()
            if valid.any():
                errors.append((float(np.mean(np.abs(truth[valid] - prediction[valid]))), model))
        if not errors:
            continue
        best_baseline = min(errors)[1]
        scenario = str(group["scenario_id"].iloc[0])
        options.append((int(pd.to_datetime(group["date"]).nunique()), scenario, group, best_baseline))
    if not options:
        raise ArtifactUnavailable(
            f"{event_type} case lacks linear, proposed q05/q95, and a distinct baseline"
        )
    _, _, selected, best = sorted(options, key=lambda item: (-item[0], item[1]))[0]
    return selected.copy(), best


def _figure_07(path: Path, daily: pd.DataFrame | None) -> dict[str, Any]:
    data = _require_frame(
        daily,
        ("date", "scenario_id", "target", "model", "y_true", "y_pred", "q05", "q95"),
        "daily event predictions",
    ).copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if "experiment" in data and data["experiment"].notna().any():
        data = data.loc[data["experiment"].astype(str).eq("M7")]
    else:
        data = data.loc[data["event_type"].notna()]
    cases: list[tuple[str, str, pd.DataFrame, str]] = []
    for label, event_type, target in (
        ("High temperature", "high_temperature", "T"),
        ("Flood peak", "flood", "F"),
        ("Long low flow", "low_flow", "F"),
    ):
        group, baseline = _select_event_case(data, event_type, target)
        cases.append((label, target, group, baseline))

    figure, axes = plt.subplots(3, 1, figsize=(11.2, 9.2), constrained_layout=True)
    selected_details = []
    for axis, (label, target, group, best_baseline) in zip(axes, cases, strict=True):
        aggregated = (
            group.groupby(["date", "model"], dropna=False, observed=True)
            .agg(y_true=("y_true", "mean"), y_pred=("y_pred", "mean"), q05=("q05", "mean"), q95=("q95", "mean"))
            .reset_index()
            .sort_values("date")
        )
        truth = aggregated.groupby("date", as_index=False)["y_true"].mean()
        axis.plot(truth["date"], truth["y_true"], color="black", linewidth=1.8, marker="o", markersize=2.5, label="observed truth")
        for start, end in _contiguous_spans(truth["date"]):
            axis.axvspan(start - pd.Timedelta(hours=12), end + pd.Timedelta(hours=12), color="#999999", alpha=0.13)
        for model, style in (("linear", "--"), (best_baseline, "-."), ("proposed", "-")):
            selected = aggregated.loc[aggregated["model"].astype(str).eq(model)]
            axis.plot(
                selected["date"], selected["y_pred"], linestyle=style, linewidth=1.4,
                color=MODEL_COLORS.get(model), label=model,
            )
            if model == "proposed":
                finite = selected[["date", "q05", "q95"]].dropna()
                axis.fill_between(finite["date"], finite["q05"], finite["q95"], color=MODEL_COLORS.get(model), alpha=0.18, label="proposed 90% interval")
        station = str(group["station_id"].iloc[0]) if "station_id" in group else ""
        axis.set_title(f"{label}: {station} ({target})")
        axis.set_ylabel("Temperature (°C)" if target == "T" else "Flow (m³ s⁻¹)")
        axis.grid(alpha=0.2)
        axis.legend(frameon=False, fontsize=7, ncol=3)
        selected_details.append(
            {
                "event": label,
                "scenario_id": str(group["scenario_id"].iloc[0]),
                "station_id": station,
                "strongest_distinct_baseline": best_baseline,
            }
        )
    axes[-1].set_xlabel("Date (shading denotes artificially hidden dates)")
    figure.suptitle("Recovery during observed high-temperature, flood, and low-flow events", fontsize=13)
    _save_figure(figure, path)
    return {"selected_cases": selected_details}


def _figure_08(path: Path, events: pd.DataFrame | None) -> dict[str, Any]:
    data = _require_frame(events, ("scenario_id", "station_id", "model", "target"), "event metrics").copy()
    semantic = pd.Series(False, index=data.index)
    if "experiment" in data:
        semantic |= data["experiment"].astype(str).eq("M10")
    if "mask_type" in data:
        semantic |= data["mask_type"].astype(str).str.lower().eq("loso")
    if "validation_scope" in data:
        semantic |= data["validation_scope"].astype(str).str.lower().str.contains("loso")
    data = data.loc[semantic & data["target"].astype(str).str.upper().eq("T")]
    if data.empty:
        raise ArtifactUnavailable("no exploratory internal LOSO temperature rows")
    if "is_external_validation" in data:
        external = data["is_external_validation"].fillna(False).astype(bool)
        if external.any():
            raise ArtifactUnavailable("LOSO rows are marked as external validation and cannot be plotted here")
    metric = next(
        (
            column for column in ("MAE", "skill")
            if column in data and pd.to_numeric(data[column], errors="coerce").notna().any()
        ),
        None,
    )
    if metric is None:
        raise ArtifactUnavailable("LOSO rows contain neither finite MAE nor skill")
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.dropna(subset=[metric])
    grouped = data.groupby(["station_id", "model"], as_index=False)[metric].mean()
    if grouped.empty:
        raise ArtifactUnavailable("LOSO summary is empty")
    stations = sorted(grouped["station_id"].astype(str).unique())
    models = _ordered_models(grouped["model"])
    x = np.arange(len(stations), dtype=float)
    width = 0.8 / max(1, len(models))
    figure, axis = plt.subplots(figsize=(7.8, 4.6), constrained_layout=True)
    for index, model in enumerate(models):
        lookup = grouped.loc[grouped["model"].astype(str).eq(model)].set_index("station_id")[metric]
        values = [lookup.get(station, np.nan) for station in stations]
        positions = x - 0.4 + width / 2 + index * width
        axis.bar(positions, values, width=width, label=model, color=MODEL_COLORS.get(model))
    axis.set_xticks(x, stations)
    axis.set_xlabel("Held-out study station")
    axis.set_ylabel("MAE (°C)" if metric == "MAE" else "Skill (vs climatology)")
    axis.set_title(LOSO_TITLE)
    axis.text(
        0.5, -0.19,
        "Training/tuning use the other study stations; this is internal spatial transfer only.",
        transform=axis.transAxes, ha="center", va="top", fontsize=8,
    )
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False, fontsize=8)
    _save_figure(figure, path)
    return {
        "validation_scope": "exploratory_internal_loso_not_external_validation",
        "is_external_validation": False,
        "stations": stations,
        "models": models,
        "metric": metric,
    }


def _table_01(
    station_metadata: pd.DataFrame | None,
    variable_summary: pd.DataFrame | None,
) -> pd.DataFrame:
    stations = _require_frame(station_metadata, ("station_id",), "station metadata").copy()
    summary = _require_frame(
        variable_summary,
        ("station_id", "variable", "coverage"),
        "EDA variable summary",
    ).copy()
    summary["coverage"] = pd.to_numeric(summary["coverage"], errors="coerce")
    coverage = (
        summary.groupby("station_id", as_index=False)
        .agg(
            variables=("variable", lambda values: ";".join(sorted(set(map(str, values))))),
            variable_count=("variable", "nunique"),
            mean_coverage=("coverage", "mean"),
            minimum_coverage=("coverage", "min"),
        )
    )
    result = stations.merge(coverage, on="station_id", how="left", validate="one_to_one")
    preferred = [
        "station_id", "station_name", "river_name", "network_order", "latitude", "longitude",
        "drainage_area_km2", "regulated_or_unregulated", "data_period", "hydrology_source",
        "met_station_id", "met_station_name", "variables", "variable_count", "mean_coverage", "minimum_coverage",
    ]
    return result[[column for column in preferred if column in result]].sort_values(
        "network_order" if "network_order" in result else "station_id"
    )


def _bootstrap_summary(
    data: pd.DataFrame,
    group_cols: Sequence[str],
    metrics: Sequence[str] = ("MAE", "RMSE", "skill"),
    *,
    n_boot: int = 1000,
    seed: int = 20260815,
) -> pd.DataFrame:
    active_groups = [column for column in group_cols if column in data]
    available_metrics = [metric for metric in metrics if metric in data]
    if not active_groups or not available_metrics:
        raise ArtifactUnavailable("result table has no grouping columns or metrics")
    rows: list[dict[str, Any]] = []
    grouped = data.groupby(active_groups, dropna=False, observed=True)
    for offset, (group_key, group) in enumerate(grouped):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key, strict=True))
        for metric in available_metrics:
            selected = group[[metric] + (["scenario_id"] if "scenario_id" in group else [])].copy()
            selected[metric] = pd.to_numeric(selected[metric], errors="coerce")
            if "scenario_id" in selected:
                values = selected.groupby("scenario_id", dropna=False)[metric].mean().dropna().to_numpy(float)
            else:
                values = selected[metric].dropna().to_numpy(float)
            if not len(values):
                continue
            if len(values) >= 2:
                rng = np.random.default_rng(seed + offset * 17 + available_metrics.index(metric))
                draws = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
                ci_lower, ci_upper = np.quantile(draws, (0.025, 0.975))
                std = float(np.std(values, ddof=1))
                reason = None
            else:
                ci_lower = ci_upper = std = np.nan
                reason = "one event unit; CI and sample standard deviation unavailable"
            rows.append(
                {
                    **metadata,
                    "metric": metric,
                    "mean": float(np.mean(values)),
                    "median": float(np.median(values)),
                    "std": std,
                    "ci_lower": float(ci_lower),
                    "ci_upper": float(ci_upper),
                    "n_events": int(len(values)),
                    "ci_method": f"percentile bootstrap over scenario_id ({n_boot} replicates)",
                    "reason": reason,
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ArtifactUnavailable("result table has no finite event metrics")
    return result


def _table_02(events: pd.DataFrame | None) -> pd.DataFrame:
    data = _require_frame(events, ("target", "model"), "event metrics").copy()
    selected = data["target"].astype(str).str.upper().eq("T")
    if "experiment" in data:
        selected &= data["experiment"].astype(str).eq("M1")
    elif "missing_rate" in data:
        selected &= pd.to_numeric(data["missing_rate"], errors="coerce").notna()
    data = data.loc[selected]
    if data.empty:
        raise ArtifactUnavailable("no M1 random-point temperature results")
    return _bootstrap_summary(
        data,
        ("station_id", "model", "missing_rate", "pattern", "target"),
    )


def _table_03(events: pd.DataFrame | None) -> pd.DataFrame:
    data = _require_frame(events, ("target", "model", "gap_length"), "event metrics").copy()
    selected = data["target"].astype(str).str.upper().eq("T")
    if "experiment" in data and data["experiment"].notna().any():
        selected &= data["experiment"].astype(str).isin(["M2", "M3"])
    elif "mask_type" in data:
        selected &= data["mask_type"].astype(str).isin(["block", "multiblock"])
    data = data.loc[selected]
    if data.empty:
        raise ArtifactUnavailable("no M2/M3 continuous-gap temperature results")
    return _bootstrap_summary(
        data,
        ("station_id", "model", "experiment", "mask_type", "gap_length", "pattern", "target"),
    )


def _table_04(events: pd.DataFrame | None) -> pd.DataFrame:
    data = _require_frame(events, ("target", "model"), "event metrics").copy()
    selected = pd.Series(False, index=data.index)
    if "experiment" in data:
        selected |= data["experiment"].astype(str).eq("M4")
    if "mask_type" in data:
        selected |= data["mask_type"].astype(str).eq("station_outage")
    data = data.loc[selected]
    if data.empty:
        raise ArtifactUnavailable("no M4 whole-station outage results")
    return _bootstrap_summary(
        data,
        ("station_id", "model", "gap_length", "pattern", "target"),
    )


def _table_05(
    frontiers: pd.DataFrame | None,
    shapley: pd.DataFrame | None,
) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    if frontiers is not None and not frontiers.empty and "statistical_frontier_days" in frontiers:
        frontier = frontiers.copy()
        frontier["section"] = "recoverability_frontier"
        frontier["component"] = "statistical_frontier_days"
        frontier["value"] = pd.to_numeric(frontier["statistical_frontier_days"], errors="coerce")
        frontier["ci_lower"] = pd.to_numeric(frontier.get("frontier_ci_lower"), errors="coerce")
        frontier["ci_upper"] = pd.to_numeric(frontier.get("frontier_ci_upper"), errors="coerce")
        pieces.append(frontier)
    if shapley is not None and not shapley.empty and {"source", "shapley"}.issubset(shapley):
        contribution = shapley.copy()
        contribution["section"] = "information_compensation"
        contribution["component"] = contribution["source"].astype(str).map(SOURCE_LABELS).fillna(contribution["source"].astype(str))
        contribution["value"] = pd.to_numeric(contribution["shapley"], errors="coerce")
        contribution["ci_lower"] = np.nan
        contribution["ci_upper"] = np.nan
        pieces.append(contribution)
    if not pieces:
        raise ArtifactUnavailable("neither recoverability frontiers nor Shapley compensation results are available")
    combined = pd.concat(pieces, ignore_index=True, sort=False)
    preferred = [
        "section", "station_id", "target", "model", "pattern", "gap_length", "component",
        "value", "ci_lower", "ci_upper", "breakpoint_days", "total_gain", "reason",
    ]
    return combined[[column for column in preferred if column in combined]].sort_values(
        [column for column in ("section", "station_id", "target", "model", "gap_length", "component") if column in combined],
        na_position="last",
    )


def generate_publication_outputs(
    *,
    daily_predictions_path: str | Path = "results/experiments/daily_predictions.parquet",
    event_metrics_path: str | Path = "results/experiments/event_metrics.parquet",
    analysis_dir: str | Path = "results/analysis",
    station_metadata_path: str | Path = "metadata/station_metadata.csv",
    eda_dir: str | Path = "results/eda",
    study_area_points_path: str | Path = "results/eda/study_area_points.csv",
    availability_image_path: str | Path = "figures/eda/availability.png",
    online_dir: str | Path = "results/online",
    figure_dir: str | Path = "figures/main",
    table_dir: str | Path = "paper/tables",
    manifest_path: str | Path = "results/final_results_manifest.json",
) -> dict[str, Any]:
    """Generate available main artifacts and freeze their exact input summaries."""

    daily_path = Path(daily_predictions_path)
    events_path = Path(event_metrics_path)
    analysis_root = Path(analysis_dir)
    eda_root = Path(eda_dir)
    online_root = Path(online_dir)
    figures = Path(figure_dir)
    tables = Path(table_dir)
    final_manifest_path = Path(manifest_path)
    inputs: dict[str, Any] = {}

    daily_raw = _load_optional_table(daily_path, inputs, "daily_predictions")
    events_raw = _load_optional_table(events_path, inputs, "event_metrics")
    station_metadata = _load_optional_table(Path(station_metadata_path), inputs, "station_metadata")
    variable_summary = _load_optional_table(eda_root / "variable_summary.csv", inputs, "eda_variable_summary")
    study_points = _load_optional_table(Path(study_area_points_path), inputs, "study_area_points")

    expected_analysis = {
        "skill_curves.csv",
        "recoverability_frontiers.csv",
        "information_shapley.csv",
        "information_compensation_gains.csv",
        "network_resilience_curve.csv",
        "network_resilience_auc.csv",
        "node_importance.csv",
        "scientific_metrics.csv",
        "paired_comparisons.csv",
        "uncertainty_by_gap.csv",
        "uncertainty_growth.csv",
        "uncertainty_overall.csv",
    }
    discovered_analysis = {path.name for path in analysis_root.glob("*.csv")} if analysis_root.exists() else set()
    analysis_tables: dict[str, pd.DataFrame | None] = {}
    for name in sorted(expected_analysis | discovered_analysis):
        analysis_tables[name] = _load_optional_table(
            analysis_root / name,
            inputs,
            f"analysis/{Path(name).stem}",
        )

    online_metrics = _load_optional_table(online_root / "metrics.csv", inputs, "online/metrics")
    online_horizons = _load_optional_table(online_root / "horizon_metrics.csv", inputs, "online/horizon_metrics")
    protocol_path = online_root / "protocol.json"
    if protocol_path.exists():
        try:
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            inputs["online/protocol"] = {"path": str(protocol_path), "status": "available", "protocol": protocol}
        except (OSError, ValueError) as error:
            inputs["online/protocol"] = {"path": str(protocol_path), "status": "unreadable", "reason": str(error)}
    else:
        inputs["online/protocol"] = {"path": str(protocol_path), "status": "missing"}

    daily = _enrich_results(daily_raw)
    events = _enrich_results(events_raw)
    figure_specs: list[tuple[str, str, Callable[[], dict[str, Any]], int | None]] = [
        (
            "figure_01", "Study area, monitoring variables, and data availability",
            lambda: _figure_01(figures / "figure_01.png", station_metadata, variable_summary, study_points, Path(availability_image_path)),
            (len(station_metadata) + len(variable_summary)) if station_metadata is not None and variable_summary is not None else None,
        ),
        (
            "figure_02", "Missingness experiments and recoverability framework",
            lambda: _figure_02(figures / "figure_02.png"), 0,
        ),
        (
            "figure_03", "Temperature recovery across core missingness conditions",
            lambda: _figure_03(figures / "figure_03.png", events), len(events) if events is not None else None,
        ),
        (
            "figure_04", "Temperature recoverability frontiers with 95% confidence intervals",
            lambda: _figure_04(figures / "figure_04.png", analysis_tables["skill_curves.csv"], analysis_tables["recoverability_frontiers.csv"]),
            len(analysis_tables["skill_curves.csv"]) if analysis_tables["skill_curves.csv"] is not None else None,
        ),
        (
            "figure_05", "Information compensation across missing-gap duration",
            lambda: _figure_05(figures / "figure_05.png", analysis_tables["information_shapley.csv"]),
            len(analysis_tables["information_shapley.csv"]) if analysis_tables["information_shapley.csv"] is not None else None,
        ),
        (
            "figure_06", "Monitoring-network resilience under station failures",
            lambda: _figure_06(figures / "figure_06.png", analysis_tables["network_resilience_curve.csv"], analysis_tables["node_importance.csv"]),
            len(analysis_tables["network_resilience_curve.csv"]) if analysis_tables["network_resilience_curve.csv"] is not None else None,
        ),
        (
            "figure_07", "Recovery during observed high-temperature, flood, and low-flow events",
            lambda: _figure_07(figures / "figure_07.png", daily), len(daily) if daily is not None else None,
        ),
        (
            "figure_08", LOSO_TITLE,
            lambda: _figure_08(figures / "figure_08.png", events), len(events) if events is not None else None,
        ),
    ]
    figure_status: dict[str, Any] = {}
    for name, title, builder, source_rows in figure_specs:
        path = figures / f"{name}.png"
        try:
            details = builder()
        except ArtifactUnavailable as error:
            if path.exists():
                path.unlink()
            figure_status[name] = _artifact_status(path, title, "skipped", reason=str(error), source_rows=source_rows)
        else:
            figure_status[name] = _artifact_status(path, title, "generated", source_rows=source_rows, details=details)

    table_specs: list[tuple[str, str, Callable[[], pd.DataFrame], int | None]] = [
        ("table_01", "Dataset and station information", lambda: _table_01(station_metadata, variable_summary), len(station_metadata) if station_metadata is not None else None),
        ("table_02", "Random-point temperature recovery", lambda: _table_02(events), len(events) if events is not None else None),
        ("table_03", "Continuous-gap temperature recovery", lambda: _table_03(events), len(events) if events is not None else None),
        ("table_04", "Whole-station outage recovery", lambda: _table_04(events), len(events) if events is not None else None),
        (
            "table_05", "Recoverability frontiers and information compensation",
            lambda: _table_05(analysis_tables["recoverability_frontiers.csv"], analysis_tables["information_shapley.csv"]),
            sum(len(frame) for frame in (analysis_tables["recoverability_frontiers.csv"], analysis_tables["information_shapley.csv"]) if frame is not None),
        ),
    ]
    table_status: dict[str, Any] = {}
    for name, title, builder, source_rows in table_specs:
        path = tables / f"{name}.csv"
        try:
            frame = builder()
        except ArtifactUnavailable as error:
            if path.exists():
                path.unlink()
            table_status[name] = _artifact_status(path, title, "skipped", reason=str(error), source_rows=source_rows)
        else:
            _write_table(frame, path)
            table_status[name] = _artifact_status(path, title, "generated", source_rows=source_rows, details={"rows": len(frame), "columns": list(frame.columns)})

    frozen_summary = {
        "daily_predictions": _frame_summary(daily),
        "event_metrics": _frame_summary(events),
        "analysis_tables": {
            name: _frame_summary(frame) for name, frame in sorted(analysis_tables.items())
        },
        "online_metrics": _frame_summary(online_metrics),
        "online_horizon_metrics": _frame_summary(online_horizons),
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "scope": "publication figures and tables (tasks 71-75)",
        "integrity_note": "Input row counts and categorical summaries are frozen; content hashes are intentionally not computed.",
        "inputs": inputs,
        "frozen_result_summary": frozen_summary,
        "figures": figure_status,
        "tables": table_status,
        "manifests": {
            "final": str(final_manifest_path),
            "figures": str(figures / "figure_manifest.json"),
            "tables": str(tables / "table_manifest.json"),
        },
    }
    _write_json(
        {
            "schema_version": 1,
            "artifacts": figure_status,
            "result_inputs": {"daily_predictions": frozen_summary["daily_predictions"], "event_metrics": frozen_summary["event_metrics"]},
        },
        figures / "figure_manifest.json",
    )
    _write_json(
        {
            "schema_version": 1,
            "artifacts": table_status,
            "result_inputs": {"event_metrics": frozen_summary["event_metrics"], "analysis_tables": frozen_summary["analysis_tables"]},
        },
        tables / "table_manifest.json",
    )
    _write_json(manifest, final_manifest_path)
    return manifest


build_publication_outputs = generate_publication_outputs


__all__ = [
    "ArtifactUnavailable",
    "LOSO_TITLE",
    "build_publication_outputs",
    "generate_publication_outputs",
]
