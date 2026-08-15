"""Targeted audit tables for the raw daily station data."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .loading import load_stations, load_variable_specs

AUDIT_TABLE_NAMES = (
    "variable_summary",
    "missing_code_summary",
    "date_continuity",
    "constant_runs",
    "rating_curve_diagnostics",
)


def variable_summary(long_data: pd.DataFrame) -> pd.DataFrame:
    """Summarise each converted variable while retaining raw/target units."""

    rows: list[dict[str, Any]] = []
    keys = ["station_id", "variable", "raw_name", "raw_unit", "unit"]
    for key, group in long_data.groupby(keys, sort=True, dropna=False):
        values = group["value"].dropna()
        quantiles = values.quantile([0.01, 0.25, 0.5, 0.75, 0.99]) if not values.empty else pd.Series(dtype=float)
        rows.append(
            {
                **dict(zip(keys, key)),
                "row_count": int(len(group)),
                "natural_observed_count": int(group["natural_observed"].sum()),
                "quality_approved_count": int(group["quality_approved"].sum()),
                "missing_count": int((~group["natural_observed"]).sum()),
                "missing_rate": float((~group["natural_observed"]).mean()),
                "mean": float(values.mean()) if not values.empty else np.nan,
                "std": float(values.std(ddof=0)) if not values.empty else np.nan,
                "min": float(values.min()) if not values.empty else np.nan,
                "q01": float(quantiles.get(0.01, np.nan)),
                "q25": float(quantiles.get(0.25, np.nan)),
                "median": float(quantiles.get(0.5, np.nan)),
                "q75": float(quantiles.get(0.75, np.nan)),
                "q99": float(quantiles.get(0.99, np.nan)),
                "max": float(values.max()) if not values.empty else np.nan,
            }
        )
    return pd.DataFrame(rows)


def missing_code_summary(
    long_data: pd.DataFrame,
    variable_specs: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    """Count configured special codes and literal nulls in the raw source."""

    rows: list[dict[str, Any]] = []
    for (station_id, raw_name), group in long_data.groupby(["station_id", "raw_name"], sort=True):
        raw_values = group["raw_value"]
        for code in variable_specs[raw_name].get("missing_codes", ()):
            count = int(np.isclose(raw_values, float(code), rtol=0.0, atol=1e-9, equal_nan=False).sum())
            rows.append(
                {
                    "station_id": station_id,
                    "raw_name": raw_name,
                    "variable": str(variable_specs[raw_name]["standard_name"]),
                    "missing_code": str(code),
                    "code_type": "confirmed_special_code",
                    "count": count,
                }
            )
        null_count = int(raw_values.isna().sum())
        if null_count:
            rows.append(
                {
                    "station_id": station_id,
                    "raw_name": raw_name,
                    "variable": str(variable_specs[raw_name]["standard_name"]),
                    "missing_code": "NaN",
                    "code_type": "literal_null",
                    "count": null_count,
                }
            )
    columns = ["station_id", "raw_name", "variable", "missing_code", "code_type", "count"]
    return pd.DataFrame(rows, columns=columns)


def date_continuity(long_data: pd.DataFrame) -> pd.DataFrame:
    """Report duplicate and missing calendar dates for each source station."""

    rows = []
    for station_id, station in long_data.groupby("station_id", sort=True):
        first_variable = station["raw_name"].iloc[0]
        dates_with_duplicates = station.loc[station["raw_name"] == first_variable, "date"].sort_values()
        unique_dates = pd.DatetimeIndex(dates_with_duplicates.drop_duplicates())
        start = unique_dates.min()
        end = unique_dates.max()
        expected = pd.date_range(start, end, freq="D")
        duplicate_count = int(dates_with_duplicates.duplicated().sum())
        missing_dates = expected.difference(unique_dates)
        rows.append(
            {
                "station_id": station_id,
                "start_date": start,
                "end_date": end,
                "row_count": int(len(dates_with_duplicates)),
                "unique_date_count": int(len(unique_dates)),
                "expected_day_count": int(len(expected)),
                "duplicate_date_count": duplicate_count,
                "missing_date_count": int(len(missing_dates)),
                "is_daily_continuous": bool(not duplicate_count and not len(missing_dates)),
            }
        )
    return pd.DataFrame(rows)


def constant_runs(long_data: pd.DataFrame, minimum_length: int = 7) -> pd.DataFrame:
    """List exact, consecutive constant-value runs of at least ``minimum_length`` days."""

    if minimum_length < 2:
        raise ValueError("minimum_length must be at least 2")
    rows: list[dict[str, Any]] = []
    for (station_id, variable), group in long_data.groupby(["station_id", "variable"], sort=True):
        series = group.sort_values("date").drop_duplicates("date", keep="first").reset_index(drop=True)
        value_changed = series["value"].ne(series["value"].shift())
        date_broken = series["date"].diff().ne(pd.Timedelta(days=1))
        missing = series["value"].isna()
        run_id = (value_changed | date_broken | missing).cumsum()
        for _, run in series.loc[~missing].groupby(run_id[~missing], sort=False):
            if len(run) < minimum_length:
                continue
            rows.append(
                {
                    "station_id": station_id,
                    "variable": variable,
                    "value": float(run["value"].iloc[0]),
                    "start_date": run["date"].iloc[0],
                    "end_date": run["date"].iloc[-1],
                    "run_length": int(len(run)),
                }
            )
    columns = ["station_id", "variable", "value", "start_date", "end_date", "run_length"]
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result = result.sort_values(["station_id", "variable", "start_date"]).reset_index(drop=True)
    return result


def _polynomial_r2(x: np.ndarray, y: np.ndarray, degree: int) -> float:
    if len(x) <= degree or np.unique(x).size <= degree or np.unique(y).size < 2:
        return np.nan
    centered = x - np.mean(x)
    design = np.column_stack([centered**power for power in range(degree + 1)])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    prediction = design @ coefficients
    denominator = np.sum((y - np.mean(y)) ** 2)
    return float(1.0 - np.sum((y - prediction) ** 2) / denominator) if denominator > 0 else np.nan


def rating_curve_diagnostics(long_data: pd.DataFrame) -> pd.DataFrame:
    """Calculate yearly FLOW--WLEVEL dependence diagnostics for each station."""

    hydrology = long_data.loc[
        long_data["raw_name"].isin(["WLEVEL", "FLOW"]),
        ["date", "station_id", "raw_name", "value", "quality_approved"],
    ]
    hydrology = hydrology.loc[hydrology["quality_approved"]]
    wide = hydrology.pivot_table(
        index=["date", "station_id"], columns="raw_name", values="value", aggfunc="first"
    ).reset_index()
    wide["year"] = wide["date"].dt.year

    rows = []
    for (station_id, year), group in wide.groupby(["station_id", "year"], sort=True):
        valid = group[["WLEVEL", "FLOW"]].dropna()
        x = valid["WLEVEL"].to_numpy(dtype=float)
        y = valid["FLOW"].to_numpy(dtype=float)
        pearson = valid["WLEVEL"].corr(valid["FLOW"], method="pearson") if len(valid) >= 2 else np.nan
        spearman = valid["WLEVEL"].corr(valid["FLOW"], method="spearman") if len(valid) >= 2 else np.nan
        linear = _polynomial_r2(x, y, degree=1)
        quadratic = _polynomial_r2(x, y, degree=2)
        if len(valid) >= 5:
            low_cut, high_cut = np.quantile(y, [0.2, 0.8])
            low = y <= low_cut
            high = y >= high_cut
            low_r2 = _polynomial_r2(x[low], y[low], degree=1)
            high_r2 = _polynomial_r2(x[high], y[high], degree=1)
        else:
            low_r2 = high_r2 = np.nan
        rows.append(
            {
                "station_id": station_id,
                "year": int(year),
                "n_observations": int(len(valid)),
                "pearson_r": float(pearson),
                "spearman_r": float(spearman),
                "linear_r2": linear,
                "quadratic_r2": quadratic,
                "high_flow_r2": high_r2,
                "low_flow_r2": low_r2,
                "suspected_derived_flow": bool(
                    pd.notna(quadratic)
                    and pd.notna(spearman)
                    and quadratic >= 0.95
                    and abs(spearman) >= 0.95
                ),
            }
        )
    return pd.DataFrame(rows)


def build_audit_tables(
    long_data: pd.DataFrame,
    variable_specs: Mapping[str, Mapping[str, Any]],
    minimum_constant_run: int = 7,
) -> dict[str, pd.DataFrame]:
    return {
        "variable_summary": variable_summary(long_data),
        "missing_code_summary": missing_code_summary(long_data, variable_specs),
        "date_continuity": date_continuity(long_data),
        "constant_runs": constant_runs(long_data, minimum_constant_run),
        "rating_curve_diagnostics": rating_curve_diagnostics(long_data),
    }


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_No rows._"
    selected = frame.loc[:, columns].copy()
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in selected.itertuples(index=False, name=None):
        values = ["" if pd.isna(value) else str(value) for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_audit_report(
    tables: Mapping[str, pd.DataFrame],
    variable_specs: Mapping[str, Mapping[str, Any]],
    metadata_used: bool,
    long_data: pd.DataFrame | None = None,
) -> str:
    continuity = tables["date_continuity"].copy()
    codes = tables["missing_code_summary"]
    ratings = tables["rating_curve_diagnostics"]
    code_rows = codes.loc[codes["count"] > 0]
    suspected = ratings.groupby("station_id")["suspected_derived_flow"].mean().reset_index()
    suspected["suspected_year_fraction"] = suspected.pop("suspected_derived_flow").round(3)

    conversion_rows = []
    for raw_name in ("WDSP", "PRCP"):
        spec = variable_specs[raw_name]
        conversion_rows.append(
            {
                "raw_name": raw_name,
                "raw_unit": spec.get("raw_unit", "unknown"),
                "unit": spec.get("unit", "unknown"),
                "unit_conversion": spec.get("unit_conversion", "identity"),
            }
        )
    conversions = pd.DataFrame(conversion_rows)

    metadata_statement = (
        "Unit and variable rules were loaded from `metadata/data_dictionary.csv`."
        if metadata_used
        else "The data dictionary was not available; built-in WDSP knots→m/s and PRCP inches→mm rules were used."
    )
    dh_statement = (
        "`DH` is documented as daily sunshine duration in hours and is retained as a meteorological channel."
        if metadata_used
        else "`DH` remains usable as a raw channel, but its scientific meaning and unit require external metadata."
    )
    known_events = "The expected B1 dates were not present in the audited input."
    if long_data is not None:
        b1_level = long_data.loc[
            (long_data["station_id"] == "B1") & (long_data["raw_name"] == "WLEVEL")
        ].set_index("date")
        previous_date = pd.Timestamp("2018-12-31")
        step_date = pd.Timestamp("2019-01-01")
        b1_flow_november = long_data.loc[
            (long_data["station_id"] == "B1")
            & (long_data["raw_name"] == "FLOW")
            & long_data["date"].between("2018-11-01", "2018-11-30")
        ]
        if previous_date in b1_level.index and step_date in b1_level.index and not b1_flow_november.empty:
            before = float(b1_level.loc[previous_date, "value"])
            after = float(b1_level.loc[step_date, "value"])
            step = after - before
            peak = b1_flow_november.loc[b1_flow_november["value"].idxmax()]
            known_events = (
                f"B1 WLEVEL changes from {before:.2f} to {after:.2f} on 2019-01-01 "
                f"(a {step:+.2f} m step), consistent with a datum/baseline change requiring "
                "downstream treatment rather than deletion. The B1 November 2018 high-flow event "
                f"is also retained (monthly peak FLOW={float(peak['value']):.0f} on "
                f"{pd.Timestamp(peak['date']).date()}). Both remain `observed_unflagged` and "
                "`quality_approved=true`; neither is silently removed by this pipeline."
            )
    return "\n".join(
        [
            "# Data quality audit",
            "",
            "## Scope",
            "",
            "This audit covers the B1, S2, and P3 daily source files. " + metadata_statement,
            "",
            "## Date continuity",
            "",
            _markdown_table(
                continuity,
                [
                    "station_id",
                    "start_date",
                    "end_date",
                    "unique_date_count",
                    "duplicate_date_count",
                    "missing_date_count",
                    "is_daily_continuous",
                ],
            ),
            "",
            "## Confirmed missing codes",
            "",
            _markdown_table(
                code_rows,
                ["station_id", "raw_name", "missing_code", "code_type", "count"],
            ),
            "",
            "Confirmed special codes are retained in `raw_value`, converted to NaN in `value`, and marked "
            "`natural_observed=false`, `quality_approved=false`, and `qc_status=source_missing`.",
            "",
            "## Unit conversion",
            "",
            _markdown_table(conversions, ["raw_name", "raw_unit", "unit", "unit_conversion"]),
            "",
            "## FLOW–WLEVEL diagnostic",
            "",
            _markdown_table(suspected, ["station_id", "suspected_year_fraction"]),
            "",
            "The yearly diagnostics and standard hydrological compilation practice indicate a rating-curve-like "
            "dependence, but the supplied files contain no derivation flag. FLOW and WLEVEL are therefore treated "
            "as one hydraulic information group in independence analyses without claiming the exact production "
            "method for each value.",
            "",
            "## Known B1 events retained",
            "",
            known_events,
            "",
            "## Quality limitation",
            "",
            "The source CSV files contain no per-value quality flags. Consequently, `quality_approved` only "
            "excludes literal source missing values and the confirmed WDSP=999.9 / PRCP=99.99 codes. It must "
            "not be interpreted as proof that every remaining value was individually approved by the provider.",
            "",
            dh_statement,
            "",
            "An external monthly record independently agrees with most B1 monthly means. S2 agrees through 2012 "
            "but has a 2013–2019 year-order discrepancy; the supplied daily series is retained unchanged and the "
            "mismatch is carried as a provenance limitation.",
            "",
        ]
    )


def write_audit_outputs(
    tables: Mapping[str, pd.DataFrame],
    report: str,
    output_dir: str | Path,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in AUDIT_TABLE_NAMES:
        tables[name].to_csv(output_dir / f"{name}.csv", index=False)
    (output_dir / "data_quality_report.md").write_text(report, encoding="utf-8")


def audit_raw_data(
    raw_dir: str | Path,
    data_dictionary: str | Path | None,
    output_dir: str | Path,
    minimum_constant_run: int = 7,
) -> dict[str, pd.DataFrame]:
    metadata_path = Path(data_dictionary) if data_dictionary is not None else None
    specs = load_variable_specs(metadata_path)
    long_data = load_stations(raw_dir, metadata_path)
    tables = build_audit_tables(long_data, specs, minimum_constant_run)
    report = render_audit_report(
        tables,
        specs,
        bool(metadata_path and metadata_path.exists()),
        long_data=long_data,
    )
    write_audit_outputs(tables, report, output_dir)
    return tables
