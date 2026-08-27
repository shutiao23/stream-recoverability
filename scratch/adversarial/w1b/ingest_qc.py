"""Station-level ingest QC (adversarial competing implementation, W1-B).

This is not production code. It exists to beat a literal reading of the
physical-range 1% gate, which accepts USGS station 13343000 on Clearwater
after two NWIS ``-999999`` sentinels (2 / 1848 ≈ 0.108%).

Stricter rule: any NWIS numeric sentinel in the value field rejects the
station (``rejected_sentinel``), before approval filtering, before the 1%
bucket, and without dropping the rest of the river.
"""

from __future__ import annotations

import argparse
import ast
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

PHYSICAL_MIN_C = -5.0
PHYSICAL_MAX_C = 45.0
RANGE_NA_REJECT_PROPORTION = 0.01
CONSTANT_RUN_DAYS = 14
JUMP_C = 10.0
MIN_APPROVED_DAYS_PER_YEAR = 300
KELVIN_MEDIAN_MIN = 260.0
KELVIN_MEDIAN_MAX = 320.0
KELVIN_OFFSET = 273.15

# NWIS / Water Data missing codes observed or adjacent. 0.0 is never a sentinel.
SENTINEL_EXACT = frozenset(
    {
        -999999.0,
        -99999.0,
        -9999.0,
        9999.0,
        99999.0,
        999999.0,
    }
)
SENTINEL_ABS_FLOOR = 9999.0

DATE_CANDIDATES = ("date", "datetime", "time", "DATE", "DateTime")
STATION_CANDIDATES = (
    "station_id",
    "site_id",
    "site_no",
    "monitoring_location_id",
)
VALUE_CANDIDATES = (
    "temperature_c",
    "temperature_degC",
    "wtemp",
    "temperature",
    "value",
)
QUALIFIER_CANDIDATES = ("qualifier", "qualifiers", "qualifier_json")
APPROVAL_CANDIDATES = ("approval_status", "approval")
# Legacy analysis-eligibility aliases. Not USGS approval.
NOT_USGS_APPROVAL = frozenset({"quality_approved", "analysis_eligible"})

REPORT_COLUMNS = (
    "station_id",
    "layout",
    "approval_source",
    "n_numeric",
    "n_sentinel",
    "sentinel_proportion",
    "n_range_na",
    "range_na_proportion",
    "naive_one_percent_verdict",
    "n_non_approved_na",
    "n_estimated_kept",
    "n_ice_flagged",
    "max_constant_run_days",
    "n_jump_days",
    "n_years_observed",
    "n_evaluable_years",
    "n_years_not_evaluable",
    "unit_handling",
    "flags",
    "verdict",
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLEARWATER_WIDE = (
    REPO_ROOT
    / "results/framework/public_rivers/clearwater_river_huc17_daily_wide.csv"
)
CLEARWATER_STATION = "13343000"


@dataclass
class Approval:
    approved: bool
    estimated: bool
    provisional: bool
    ice: bool
    equipment: bool
    discontinued: bool
    source: str


@dataclass
class StationQC:
    station_id: str
    layout: str
    approval_source: str
    n_numeric: int
    n_sentinel: int
    n_range_na: int
    n_non_approved_na: int
    n_estimated_kept: int
    n_ice_flagged: int
    max_constant_run_days: int
    n_jump_days: int
    n_years_observed: int
    n_evaluable_years: int
    n_years_not_evaluable: int
    unit_handling: str
    flags: tuple[str, ...]
    verdict: str
    naive_one_percent_verdict: str
    cleaned: pd.Series = field(repr=False)

    @property
    def sentinel_proportion(self) -> float:
        if self.n_numeric == 0:
            return 0.0
        return self.n_sentinel / self.n_numeric

    @property
    def range_na_proportion(self) -> float:
        if self.n_numeric == 0:
            return 0.0
        return self.n_range_na / self.n_numeric

    def as_row(self) -> dict[str, Any]:
        return {
            "station_id": self.station_id,
            "layout": self.layout,
            "approval_source": self.approval_source,
            "n_numeric": self.n_numeric,
            "n_sentinel": self.n_sentinel,
            "sentinel_proportion": self.sentinel_proportion,
            "n_range_na": self.n_range_na,
            "range_na_proportion": self.range_na_proportion,
            "naive_one_percent_verdict": self.naive_one_percent_verdict,
            "n_non_approved_na": self.n_non_approved_na,
            "n_estimated_kept": self.n_estimated_kept,
            "n_ice_flagged": self.n_ice_flagged,
            "max_constant_run_days": self.max_constant_run_days,
            "n_jump_days": self.n_jump_days,
            "n_years_observed": self.n_years_observed,
            "n_evaluable_years": self.n_evaluable_years,
            "n_years_not_evaluable": self.n_years_not_evaluable,
            "unit_handling": self.unit_handling,
            "flags": ";".join(self.flags),
            "verdict": self.verdict,
        }


def is_nwis_numeric_sentinel(value: Any) -> bool:
    """True for NWIS missing codes in the numeric value field.

    Zero is a legal temperature (freezing / ice) and is never a sentinel.
    """

    if value is None or (isinstance(value, str) and not str(value).strip()):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(number):
        return False
    if number == 0.0:
        return False
    if number in SENTINEL_EXACT:
        return True
    nearest = round(number)
    if abs(number - nearest) > 1e-9:
        return False
    return abs(nearest) >= SENTINEL_ABS_FLOOR


def naive_one_percent_verdict(values: Iterable[Any]) -> str:
    """Literal spec gate: NA-ize < -5 or > 45 °C; reject only if share > 1%.

    This is the rule that accepts Clearwater 13343000 and must not be used
    as the sentinel detector.
    """

    numeric = []
    n_range = 0
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        numeric.append(number)
        if number < PHYSICAL_MIN_C or number > PHYSICAL_MAX_C:
            n_range += 1
    if not numeric:
        return "accepted"
    if n_range / len(numeric) > RANGE_NA_REJECT_PROPORTION:
        return "rejected_sentinel"
    return "accepted"


def parse_qualifier_tokens(value: Any) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ()
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, (list, tuple)):
            return tuple(str(item).strip() for item in parsed if str(item).strip())
    pieces: list[str] = []
    for chunk in re.split(r"[:;,|/]+", text):
        token = chunk.strip().strip("'\"")
        if token:
            pieces.append(token)
    return tuple(pieces)


def classify_approval(
    tokens: Sequence[str],
    approval_status: Any = None,
    *,
    quality_approved: Any = None,
) -> Approval:
    """Map NWIS dv codes and Water Data API approval_status.

    Estimated-Approved is kept and flagged. ``quality_approved`` is ignored:
    in this repo it is a legacy alias of ``analysis_eligible``, not USGS A.
    """

    del quality_approved  # never USGS approval
    normalized = tuple(token.strip() for token in tokens if str(token).strip())
    upper = tuple(token.upper() for token in normalized)
    status = "" if approval_status is None or pd.isna(approval_status) else str(
        approval_status
    ).strip()
    status_upper = status.upper()

    ice = any(token == "ICE" or token.startswith("ICE") for token in upper)
    equipment = any(token in {"EQP", "EQUIPMENT"} or "EQUIP" in token for token in upper)
    discontinued = any(token in {"DIS", "DISCONTINUED"} for token in upper)
    estimated = any(
        token in {"E", "EST", "ESTIMATED"} or "ESTIMAT" in token for token in upper
    ) or status_upper == "ESTIMATED"
    has_a = any(token == "A" or token == "APPROVED" for token in upper)
    has_p = any(token == "P" or token == "PROVISIONAL" for token in upper)

    if status_upper == "APPROVED":
        approved = True
        provisional = False
        source = "water_data_api"
    elif status_upper == "PROVISIONAL":
        approved = False
        provisional = True
        source = "water_data_api"
    elif status_upper == "ESTIMATED":
        # API Estimated is not a provisional drop. Keep as flagged.
        approved = True
        provisional = False
        estimated = True
        source = "water_data_api"
    elif has_a:
        approved = True
        provisional = False
        source = "nwis_dv"
    elif has_p:
        approved = False
        provisional = True
        source = "nwis_dv"
    elif normalized or status:
        approved = False
        provisional = False
        source = "nwis_dv" if normalized else "water_data_api"
    else:
        approved = True  # no provider code: keep; year rule uses usable days
        provisional = False
        source = "absent"

    if equipment or discontinued:
        approved = False
    return Approval(
        approved=approved,
        estimated=estimated,
        provisional=provisional,
        ice=ice,
        equipment=equipment,
        discontinued=discontinued,
        source=source,
    )


def _first_present(columns: Iterable[str], candidates: Sequence[str]) -> str | None:
    lower = {str(name).lower(): str(name) for name in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def detect_layout(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    station_col = _first_present(columns, STATION_CANDIDATES)
    value_col = _first_present(columns, VALUE_CANDIDATES)
    if station_col and value_col:
        return "long"
    date_col = _first_present(columns, DATE_CANDIDATES)
    if date_col and len(columns) >= 2:
        return "wide"
    if isinstance(frame.index, pd.DatetimeIndex) and len(columns) >= 1:
        return "wide"
    raise ValueError("cannot detect wide vs long temperature layout")


def _normalize_station_id(value: Any) -> str:
    text = str(value).strip()
    if text.upper().startswith("USGS-"):
        text = text[5:]
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text


def _as_datetime_index(values: pd.Series | pd.DatetimeIndex) -> pd.DatetimeIndex:
    dates = pd.to_datetime(values, errors="coerce", utc=True)
    if isinstance(dates, pd.DatetimeIndex):
        index = dates
    else:
        index = pd.DatetimeIndex(dates)
    return index.tz_convert(None).tz_localize(None).normalize()


def frame_to_station_tables(frame: pd.DataFrame) -> tuple[str, list[pd.DataFrame]]:
    """Return (layout, per-station long tables) with canonical columns."""

    data = frame.copy()
    if data.columns.duplicated().any():
        raise ValueError("duplicate columns")
    layout = detect_layout(data)
    if layout == "wide":
        date_col = _first_present(data.columns, DATE_CANDIDATES)
        if date_col is not None:
            dates = _as_datetime_index(data[date_col])
            stations = [column for column in data.columns if column != date_col]
            values = data[stations]
        elif isinstance(data.index, pd.DatetimeIndex):
            dates = _as_datetime_index(data.index)
            values = data
            stations = list(data.columns)
        else:
            raise ValueError("wide frame needs a date column or DatetimeIndex")
        tables = []
        for station in stations:
            tables.append(
                pd.DataFrame(
                    {
                        "station_id": _normalize_station_id(station),
                        "date": dates,
                        "value": pd.to_numeric(values[station], errors="coerce"),
                        "qualifier": pd.NA,
                        "approval_status": pd.NA,
                        "quality_approved": pd.NA,
                    }
                )
            )
        return layout, tables

    station_col = _first_present(data.columns, STATION_CANDIDATES)
    value_col = _first_present(data.columns, VALUE_CANDIDATES)
    date_col = _first_present(data.columns, DATE_CANDIDATES)
    if station_col is None or value_col is None or date_col is None:
        raise ValueError("long frame needs station, date, and temperature columns")
    qualifier_col = _first_present(data.columns, QUALIFIER_CANDIDATES)
    approval_col = _first_present(data.columns, APPROVAL_CANDIDATES)
    quality_col = _first_present(data.columns, tuple(NOT_USGS_APPROVAL))
    long = pd.DataFrame(
        {
            "station_id": data[station_col].map(_normalize_station_id),
            "date": _as_datetime_index(data[date_col]),
            "value": pd.to_numeric(data[value_col], errors="coerce"),
            "qualifier": data[qualifier_col] if qualifier_col else pd.NA,
            "approval_status": data[approval_col] if approval_col else pd.NA,
            "quality_approved": data[quality_col] if quality_col else pd.NA,
        }
    )
    tables = [group.copy() for _, group in long.groupby("station_id", sort=True)]
    return layout, tables


def _approval_source_for_table(table: pd.DataFrame) -> str:
    has_qual = table["qualifier"].notna().any()
    has_status = table["approval_status"].notna().any()
    has_legacy = table["quality_approved"].notna().any()
    if has_status:
        return "water_data_api"
    if has_qual:
        return "nwis_dv"
    if has_legacy:
        return "ignored_quality_approved_not_usgs"
    return "absent"


def maybe_convert_kelvin(values: np.ndarray) -> tuple[np.ndarray, str]:
    """Convert only when the series itself looks like Kelvin (~273).

    Do not assume units from the column name or from a single out-of-range
    spike. 0 °C stays 0 °C.
    """

    working = np.array(values, dtype=float, copy=True)
    finite = working[np.isfinite(working)]
    if finite.size == 0:
        return working, "assumed_celsius"
    median = float(np.median(finite))
    if PHYSICAL_MIN_C <= median <= PHYSICAL_MAX_C:
        return working, "assumed_celsius"
    kelvin_like = (
        KELVIN_MEDIAN_MIN <= median <= KELVIN_MEDIAN_MAX
        and float(np.mean((finite >= KELVIN_MEDIAN_MIN) & (finite <= KELVIN_MEDIAN_MAX)))
        >= 0.8
    )
    if not kelvin_like:
        return working, "assumed_celsius"
    finite_mask = np.isfinite(working)
    working[finite_mask] = working[finite_mask] - KELVIN_OFFSET
    return working, "converted_kelvin_median_near_273"


def _longest_constant_run(dates: pd.DatetimeIndex, values: np.ndarray) -> int:
    best = 0
    run = 0
    previous_date = None
    previous_value = None
    for date, value in zip(dates, values):
        if not np.isfinite(value) or pd.isna(date):
            run = 0
            previous_date = None
            previous_value = None
            continue
        if (
            previous_date is not None
            and previous_value is not None
            and (date - previous_date).days == 1
            and math.isclose(float(value), float(previous_value), abs_tol=1e-9)
        ):
            run += 1
        else:
            run = 1
        best = max(best, run)
        previous_date = date
        previous_value = float(value)
    return best


def _jump_days(dates: pd.DatetimeIndex, values: np.ndarray) -> int:
    """Count day-to-day |Δ| > 10 °C on consecutive calendar days.

    This is not |x - median| > 10, which would flag ordinary seasonal range.
    """

    count = 0
    previous_date = None
    previous_value = None
    for date, value in zip(dates, values):
        if not np.isfinite(value) or pd.isna(date):
            previous_date = None
            previous_value = None
            continue
        if (
            previous_date is not None
            and previous_value is not None
            and (date - previous_date).days == 1
            and abs(float(value) - float(previous_value)) > JUMP_C
        ):
            count += 1
        previous_date = date
        previous_value = float(value)
    return count


def _year_coverage(dates: pd.DatetimeIndex, usable: np.ndarray) -> tuple[int, int, int]:
    keep = np.isfinite(usable) & ~pd.isna(dates)
    if not bool(keep.any()):
        return 0, 0, 0
    unique_days = pd.DatetimeIndex(dates[keep]).unique()
    counts = pd.Series(unique_days.year).value_counts()
    n_obs = int(len(counts))
    n_eval = int((counts >= MIN_APPROVED_DAYS_PER_YEAR).sum())
    return n_obs, n_eval, n_obs - n_eval


def qc_station(table: pd.DataFrame, *, layout: str) -> StationQC:
    station_id = _normalize_station_id(table["station_id"].iloc[0])
    ordered = table.sort_values("date")
    dates = pd.DatetimeIndex(ordered["date"])
    raw = pd.to_numeric(ordered["value"], errors="coerce").to_numpy(dtype=float)
    n_numeric = int(np.isfinite(raw).sum())

    sentinel_mask = np.array([is_nwis_numeric_sentinel(value) for value in raw], dtype=bool)
    n_sentinel = int(sentinel_mask.sum())
    naive = naive_one_percent_verdict(raw[np.isfinite(raw)])

    working = raw.copy()
    working[sentinel_mask] = np.nan
    working, unit_handling = maybe_convert_kelvin(working)

    range_mask = np.isfinite(working) & (
        (working < PHYSICAL_MIN_C) | (working > PHYSICAL_MAX_C)
    )
    n_range_na = int(range_mask.sum())
    working[range_mask] = np.nan

    approval_source = _approval_source_for_table(ordered)
    n_non_approved = 0
    n_estimated = 0
    n_ice = 0
    if approval_source in {"nwis_dv", "water_data_api"}:
        for index, (_, row) in enumerate(ordered.iterrows()):
            approval = classify_approval(
                parse_qualifier_tokens(row["qualifier"]),
                row["approval_status"],
                quality_approved=row["quality_approved"],
            )
            if approval.ice:
                n_ice += 1
            if approval.estimated and approval.approved:
                n_estimated += 1
            if not approval.approved:
                if np.isfinite(working[index]):
                    n_non_approved += 1
                working[index] = np.nan

    max_run = _longest_constant_run(dates, working)
    n_jumps = _jump_days(dates, working)
    n_years, n_eval, n_not = _year_coverage(dates, working)

    flags: list[str] = []
    if max_run > CONSTANT_RUN_DAYS:
        flags.append("suspect_constant_run")
    if n_jumps:
        flags.append("suspect_jump")
    if n_estimated:
        flags.append("estimated_approved")
    if n_ice:
        flags.append("ice_affected")
    if unit_handling == "converted_kelvin_median_near_273":
        flags.append("unit_converted_kelvin")
    if approval_source == "ignored_quality_approved_not_usgs":
        flags.append("quality_approved_ignored")

    if n_sentinel > 0:
        verdict = "rejected_sentinel"
    elif n_numeric and (n_range_na / n_numeric) > RANGE_NA_REJECT_PROPORTION:
        verdict = "rejected_sentinel"
    elif n_eval == 0:
        verdict = "rejected_insufficient_years"
    elif flags:
        verdict = "accepted_with_flags"
    else:
        verdict = "accepted"

    cleaned = pd.Series(working, index=dates, name=station_id)
    return StationQC(
        station_id=station_id,
        layout=layout,
        approval_source=approval_source,
        n_numeric=n_numeric,
        n_sentinel=n_sentinel,
        n_range_na=n_range_na,
        n_non_approved_na=n_non_approved,
        n_estimated_kept=n_estimated,
        n_ice_flagged=n_ice,
        max_constant_run_days=max_run,
        n_jump_days=n_jumps,
        n_years_observed=n_years,
        n_evaluable_years=n_eval,
        n_years_not_evaluable=n_not,
        unit_handling=unit_handling,
        flags=tuple(flags),
        verdict=verdict,
        naive_one_percent_verdict=naive,
        cleaned=cleaned,
    )


def run_ingest_qc(source: pd.DataFrame | str | Path) -> tuple[pd.DataFrame, list[StationQC]]:
    """QC every station. Never emit a whole-river verdict."""

    if isinstance(source, (str, Path)):
        path = Path(source)
        frame = pd.read_csv(path)
    else:
        frame = source
    layout, tables = frame_to_station_tables(frame)
    reports = [qc_station(table, layout=layout) for table in tables]
    rows = [report.as_row() for report in reports]
    result = pd.DataFrame(rows, columns=list(REPORT_COLUMNS))
    return result, reports


def write_ingest_qc_report(
    report: pd.DataFrame,
    path: str | Path,
) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(dest, index=False)
    return dest


def clearwater_one_percent_counterexample(
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Numeric proof that the 1% rule accepts station 13343000."""

    wide_path = Path(path) if path is not None else CLEARWATER_WIDE
    wide = pd.read_csv(wide_path)
    if CLEARWATER_STATION not in wide.columns:
        raise KeyError(f"{wide_path} has no column {CLEARWATER_STATION}")
    values = pd.to_numeric(wide[CLEARWATER_STATION], errors="coerce")
    numeric = values[np.isfinite(values.to_numpy(dtype=float))]
    n_numeric = int(numeric.shape[0])
    n_sentinel = int(sum(is_nwis_numeric_sentinel(value) for value in numeric))
    n_range = int(((numeric < PHYSICAL_MIN_C) | (numeric > PHYSICAL_MAX_C)).sum())
    proportion = n_sentinel / n_numeric if n_numeric else 0.0
    range_proportion = n_range / n_numeric if n_numeric else 0.0
    sentinels_to_trip_one_percent = math.floor(RANGE_NA_REJECT_PROPORTION * n_numeric) + 1
    return {
        "path": str(wide_path),
        "station_id": CLEARWATER_STATION,
        "n_numeric": n_numeric,
        "n_sentinel": n_sentinel,
        "n_physical_range_na": n_range,
        "sentinel_proportion": proportion,
        "range_na_proportion": range_proportion,
        "one_percent": RANGE_NA_REJECT_PROPORTION,
        "naive_verdict": naive_one_percent_verdict(numeric.tolist()),
        "competing_rule": "any NWIS numeric sentinel in the value field -> rejected_sentinel",
        "sentinels_needed_to_trip_one_percent": sentinels_to_trip_one_percent,
        "shortfall_vs_one_percent": sentinels_to_trip_one_percent - n_sentinel,
    }


def covariance_poison_summary(path: str | Path | None = None) -> dict[str, Any]:
    """Show how two -999999 values destroy a donor correlation on Clearwater."""

    wide_path = Path(path) if path is not None else CLEARWATER_WIDE
    wide = pd.read_csv(wide_path, parse_dates=["date"])
    donor = pd.to_numeric(wide[CLEARWATER_STATION], errors="coerce")
    other = pd.to_numeric(wide["13342500"], errors="coerce")
    both = donor.notna() & other.notna()
    poisoned = {
        "n_overlap": int(both.sum()),
        "corr": float(donor[both].corr(other[both])),
        "donor_mean": float(donor[both].mean()),
        "donor_std": float(donor[both].std()),
    }
    cleaned = donor.mask(donor.map(is_nwis_numeric_sentinel))
    ok = cleaned.notna() & other.notna()
    repaired = {
        "n_overlap": int(ok.sum()),
        "corr": float(cleaned[ok].corr(other[ok])),
        "donor_mean": float(cleaned[ok].mean()),
        "donor_std": float(cleaned[ok].std()),
    }
    return {"poisoned": poisoned, "sentinel_na_ized": repaired}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Station-level ingest QC (W1-B competing).")
    parser.add_argument(
        "input",
        nargs="?",
        default=str(CLEARWATER_WIDE),
        help="Wide or long daily temperature CSV",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "ingest_qc_report.csv"),
    )
    parser.add_argument(
        "--clearwater-out",
        default=str(Path(__file__).resolve().parent / "clearwater_qc.csv"),
    )
    args = parser.parse_args(argv)
    report, _ = run_ingest_qc(args.input)
    write_ingest_qc_report(report, args.out)
    if Path(args.input).resolve() == CLEARWATER_WIDE.resolve():
        write_ingest_qc_report(report, args.clearwater_out)
        proof = clearwater_one_percent_counterexample(args.input)
        print(
            f"1% counterexample: {proof['n_sentinel']}/{proof['n_numeric']} = "
            f"{proof['sentinel_proportion']:.6%} < 1% -> naive {proof['naive_verdict']}"
        )
    print(report.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
