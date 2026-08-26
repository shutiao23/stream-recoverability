"""Station-level ingest QC for public USGS/EA temperature series.

This module is **not** the Jinsha ``quality_approved`` / ``analysis_eligible``
contract in ``quality.py``. Do not treat a ``quality_approved`` column as a
USGS approval code. Approval here means provider codes such as NWIS ``A``.

Physical range NA-izes values ``< -5`` °C or ``> 45`` °C. A 1% NA-ized
fraction of *out-of-range physical values* can reject a station as
``rejected_out_of_range``. That 1% rule is **not** enough for NWIS sentinel
leakage: Clearwater station ``13343000`` has only two ``-999999`` values
(~0.108% of non-null) but those are classic NWIS missing-value encodings,
not cold water. Any sentinel in the value field ⇒ ``rejected_sentinel``.

Classic NWIS sentinels counted in ``n_sentinel`` (then NA-ized):
``-999999``, ``-99999``, ``-9999``, ``9999``, ``99999``, ``999999``, and exact
integer members of that all-nines family (magnitude ``10**k - 1`` for
``k >= 4``, including the float encoding ``-999999.0``). ``50`` °C is
out-of-range, not a sentinel. ``0.0`` °C is legal ice/freezing and is never
a sentinel.

Estimated-approved provider codes (``A,e`` / Approved+Estimated) stay in the
series and are flagged; they are not provisional drops. Ice is a qualifier
flag, not a numeric sentinel. A Kelvin-like median (~273) is a note/flag
only — this module does not convert the corpus.

This gate is station-level. It does not drop a whole river; a later network
filter may drop a river if too few stations remain.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PHYSICAL_MIN_C = -5.0
PHYSICAL_MAX_C = 45.0
OUT_OF_RANGE_REJECT_FRACTION = 0.01
CONSTANT_RUN_MAX_OK_DAYS = 14
JUMP_THRESHOLD_C = 10.0
MIN_EVALUABLE_SITE_YEAR_DAYS = 300
SENTINEL_ALL_NINES_MIN_DIGITS = 4
SENTINEL_ALL_NINES_MAX_DIGITS = 12
KELVIN_MEDIAN_MIN = 260.0
KELVIN_MEDIAN_MAX = 320.0
KELVIN_BAND_FRACTION = 0.8

APPROVED_TOKENS = frozenset({"a", "approved"})
PROVISIONAL_TOKENS = frozenset({"p", "provisional"})
DROP_TOKENS = PROVISIONAL_TOKENS | frozenset({"eqp", "equipment", "dis", "discontinued"})
ESTIMATED_TOKENS = frozenset({"e", "est", "estimated"})

SITE_COLUMN_ALIASES = ("site_id", "station_id", "site_no", "site")
VALUE_COLUMN_ALIASES = ("value", "temperature_c", "temp_c", "temperature", "wtemp")
DATE_COLUMN_ALIASES = ("date", "datetime", "time")
# USGS/EA provider codes only. Never include quality_approved (Jinsha eligibility).
# Bare "cd" is too greedy (binds unrelated columns); use quality_cd instead.
APPROVAL_STATUS_COLUMN_ALIASES = (
    "approval_status",
    "approval",
    "approval_code",
)
QUALIFIER_COLUMN_ALIASES = (
    "qualifier",
    "qualifiers",
    "qual",
    "quality_cd",
    "qualifier_json",
)
APPROVAL_COLUMN_ALIASES = APPROVAL_STATUS_COLUMN_ALIASES + QUALIFIER_COLUMN_ALIASES

REPORT_COLUMNS = (
    "site_id",
    "n_raw",
    "n_sentinel",
    "n_out_of_range",
    "n_provisional_dropped",
    "n_constant_run_days",
    "n_jump",
    "qualified_years",
    "verdict",
    "notes",
)

VERDICT_ACCEPTED = "accepted"
VERDICT_ACCEPTED_WITH_FLAGS = "accepted_with_flags"
VERDICT_REJECTED_SENTINEL = "rejected_sentinel"
VERDICT_REJECTED_OUT_OF_RANGE = "rejected_out_of_range"

_TOKEN_SPLIT = re.compile(r"[\s,;|/+]+")


def is_nwis_sentinel_value(value: float) -> bool:
    """Return True for classic NWIS integer missing-value encodings.

    Matches ``-999999``, ``-99999``, ``-9999``, ``99999``, ``999999``, and
    the same all-nines integer family (at least four 9s) stored as floats.
    Physical impossibilities such as ``50`` °C or ``46`` °C are *not*
    sentinels; they belong in ``n_out_of_range``. ``0.0`` °C is never a
    sentinel.
    """

    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(number) or number == 0.0:
        return False
    return bool(_sentinel_mask(np.asarray([number], dtype=float))[0])


def _sentinel_mask(values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    finite = np.isfinite(x)
    nearest = np.zeros_like(x)
    np.round(x, out=nearest)
    exact_int = finite & (np.abs(x - nearest) <= 1e-9)
    magnitudes = np.zeros(x.shape, dtype=np.int64)
    magnitudes[exact_int] = np.abs(nearest[exact_int]).astype(np.int64)
    all_nines = np.zeros(x.shape, dtype=bool)
    for digits in range(SENTINEL_ALL_NINES_MIN_DIGITS, SENTINEL_ALL_NINES_MAX_DIGITS + 1):
        all_nines |= magnitudes == (10**digits - 1)
    # 0.0 is a legal temperature; the all-nines family never includes it.
    return exact_int & all_nines & (x != 0.0)


def _out_of_range_mask(values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    finite = np.isfinite(x)
    return finite & ((x < PHYSICAL_MIN_C) | (x > PHYSICAL_MAX_C))


def _kelvin_like(values: np.ndarray) -> bool:
    """True when the series median looks like Kelvin, not Celsius.

    Detection only. Does not convert values or relabel the reject as sentinel.
    """

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return False
    median = float(np.median(finite))
    if not (KELVIN_MEDIAN_MIN <= median <= KELVIN_MEDIAN_MAX):
        return False
    in_band = (finite >= KELVIN_MEDIAN_MIN) & (finite <= KELVIN_MEDIAN_MAX)
    return float(np.mean(in_band)) >= KELVIN_BAND_FRACTION


def _is_missing_code(code: Any) -> bool:
    if code is None:
        return True
    if isinstance(code, (list, tuple, np.ndarray, pd.Series)):
        return False
    try:
        if pd.isna(code):
            return True
    except (TypeError, ValueError):
        return False
    if isinstance(code, str) and not code.strip():
        return True
    return False


def _provider_tokens(code: Any) -> tuple[str, ...]:
    if _is_missing_code(code):
        return ()
    if isinstance(code, (list, tuple, np.ndarray)):
        pieces: list[str] = []
        for item in code:
            pieces.extend(_provider_tokens(item))
        return tuple(pieces)
    text = str(code).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ()
    cleaned = (
        text.replace("[", " ")
        .replace("]", " ")
        .replace("'", " ")
        .replace('"', " ")
        .replace("+", " ")
    )
    tokens = [
        token.strip().lower().strip("*")
        for token in _TOKEN_SPLIT.split(cleaned)
        if token.strip()
    ]
    return tuple(token for token in tokens if token)


def _classify_provider_code(code: Any) -> tuple[bool, bool, bool]:
    """Return ``(keep, estimated, ice)`` for one USGS/EA provider-code cell.

    Estimated-approved (``A,e`` / Approved+Estimated / Estimated-as-status)
    is kept and flagged. ``P`` / Provisional / ``Dis`` / ``Eqp`` are dropped.
    Ice is a qualifier flag, not a drop by itself and not a numeric sentinel.
    """

    tokens = _provider_tokens(code)
    if not tokens:
        return False, False, False
    ice = any(token == "ice" or token.startswith("ice") for token in tokens)
    estimated = any(token in ESTIMATED_TOKENS or "estimat" in token for token in tokens)
    drop = any(token in DROP_TOKENS or "equip" in token for token in tokens)
    has_approved = any(token in APPROVED_TOKENS for token in tokens)
    estimated_status = any(token == "estimated" for token in tokens)
    keep = (not drop) and (has_approved or estimated_status)
    return keep, estimated, ice


def _classify_codes(
    codes: Sequence[Any] | np.ndarray | pd.Series,
    n: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    series = pd.Series(codes)
    if len(series) != n:
        raise ValueError("approval_codes must align with dates/values")
    keep = np.empty(n, dtype=bool)
    estimated = np.empty(n, dtype=bool)
    ice = np.empty(n, dtype=bool)
    for index, item in enumerate(series):
        keep[index], estimated[index], ice[index] = _classify_provider_code(item)
    return keep, estimated, ice


def _join_code_parts(*parts: Any) -> str:
    texts: list[str] = []
    for part in parts:
        if _is_missing_code(part):
            continue
        if isinstance(part, (list, tuple, np.ndarray)):
            joined = _join_code_parts(*part)
            if joined:
                texts.append(joined)
            continue
        text = str(part).strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            texts.append(text)
    return ",".join(texts)


def _combined_approval_codes(
    group: pd.DataFrame,
    qual_col: str | None,
    status_col: str | None,
) -> pd.Series | None:
    if qual_col is None and status_col is None:
        return None
    if qual_col is not None and status_col is not None:
        return pd.Series(
            [
                _join_code_parts(qual, status)
                for qual, status in zip(group[qual_col].tolist(), group[status_col].tolist())
            ],
            index=group.index,
        )
    column = qual_col if qual_col is not None else status_col
    assert column is not None
    return group[column]


def _as_datetime_index(dates: Sequence[Any] | np.ndarray | pd.Series | pd.Index) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(dates, errors="coerce"))
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    return index.normalize()


def _numeric_values(values: Sequence[Any] | np.ndarray | pd.Series) -> np.ndarray:
    return pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)


def _count_constant_run_days(dates: pd.DatetimeIndex, values: np.ndarray) -> int:
    """Days belonging to consecutive-calendar runs of the same finite value, length > 14."""

    if len(values) == 0:
        return 0
    order = np.argsort(dates.to_numpy(dtype="datetime64[ns]"), kind="mergesort")
    ordered_dates = dates[order]
    ordered_values = values[order]
    unique_days: list[pd.Timestamp] = []
    unique_values: list[float] = []
    for day, value in zip(ordered_dates, ordered_values):
        if not unique_days or day != unique_days[-1]:
            unique_days.append(day)
            unique_values.append(float(value))
            continue
        if unique_values[-1] != float(value):
            unique_values[-1] = np.nan
    if not unique_days:
        return 0
    day_index = pd.DatetimeIndex(unique_days)
    day_values = np.asarray(unique_values, dtype=float)
    counted = 0
    run_start = 0
    for i in range(1, len(day_values) + 1):
        ended = i == len(day_values)
        if not ended:
            gap = int((day_index[i] - day_index[i - 1]).days)
            same = (
                np.isfinite(day_values[i])
                and np.isfinite(day_values[i - 1])
                and day_values[i] == day_values[i - 1]
            )
            if gap == 1 and same:
                continue
        run_len = i - run_start
        run_vals = day_values[run_start:i]
        if run_len > CONSTANT_RUN_MAX_OK_DAYS and np.isfinite(run_vals).all():
            counted += run_len
        run_start = i
    return int(counted)


def _count_jumps(dates: pd.DatetimeIndex, values: np.ndarray) -> int:
    """Count |ΔT| > 10 °C for intra-day pairs and consecutive calendar days."""

    if len(values) < 2:
        return 0
    order = np.argsort(dates.to_numpy(dtype="datetime64[ns]"), kind="mergesort")
    ordered_dates = dates[order]
    ordered_values = values[order]
    n_jump = 0
    for i in range(1, len(ordered_values)):
        if not np.isfinite(ordered_values[i]) or not np.isfinite(ordered_values[i - 1]):
            continue
        gap = int((ordered_dates[i] - ordered_dates[i - 1]).days)
        if gap not in (0, 1):
            continue
        if abs(float(ordered_values[i]) - float(ordered_values[i - 1])) > JUMP_THRESHOLD_C:
            n_jump += 1
    return int(n_jump)


def _qualified_years(dates: pd.DatetimeIndex) -> int:
    unique = pd.DatetimeIndex(dates).unique()
    if len(unique) == 0:
        return 0
    year_counts = pd.Series(unique.year).value_counts()
    return int((year_counts >= MIN_EVALUABLE_SITE_YEAR_DAYS).sum())


def _verdict(
    *,
    n_raw: int,
    n_sentinel: int,
    n_out_of_range: int,
    n_constant_run_days: int,
    n_jump: int,
    estimated_approved: bool = False,
    ice_affected: bool = False,
    suspect_kelvin: bool = False,
) -> str:
    # Any NWIS sentinel in the value field rejects the station. The 1% NA-ized
    # rule does not catch Clearwater 13343000 (two -999999 values, ~0.108%).
    if n_sentinel > 0:
        return VERDICT_REJECTED_SENTINEL
    oor_fraction = (n_out_of_range / n_raw) if n_raw else 0.0
    if oor_fraction > OUT_OF_RANGE_REJECT_FRACTION:
        return VERDICT_REJECTED_OUT_OF_RANGE
    if (
        n_out_of_range > 0
        or n_constant_run_days > 0
        or n_jump > 0
        or estimated_approved
        or ice_affected
        or suspect_kelvin
    ):
        return VERDICT_ACCEPTED_WITH_FLAGS
    return VERDICT_ACCEPTED


def _notes(
    *,
    approval_codes_absent: bool,
    n_constant_run_days: int,
    n_jump: int,
    n_out_of_range: int,
    estimated_approved: bool = False,
    ice_affected: bool = False,
    suspect_kelvin: bool = False,
) -> str:
    parts: list[str] = []
    if approval_codes_absent:
        parts.append("approval_codes_absent")
    if estimated_approved:
        parts.append("estimated_approved")
    if ice_affected:
        parts.append("ice_affected")
    if suspect_kelvin:
        parts.append("suspect_kelvin_units")
    if n_constant_run_days > 0:
        parts.append("suspect_constant_run")
    if n_jump > 0:
        parts.append("suspect_jump")
    if n_out_of_range > 0:
        parts.append("out_of_range_naized")
    return ";".join(parts)


def qc_station_series(
    dates: Sequence[Any] | np.ndarray | pd.Series | pd.Index,
    values: Sequence[Any] | np.ndarray | pd.Series,
    *,
    site_id: str,
    approval_codes: Sequence[Any] | np.ndarray | pd.Series | None = None,
) -> dict[str, Any]:
    """QC one station time series and return one ingest-report row."""

    date_index = _as_datetime_index(dates)
    raw = _numeric_values(values)
    if len(date_index) != len(raw):
        raise ValueError("dates and values must have the same length")
    valid_date = ~date_index.isna()
    codes = None
    if approval_codes is not None:
        code_array = np.asarray(approval_codes, dtype=object)
        if len(code_array) != len(valid_date):
            raise ValueError("approval_codes must align with dates/values")
        codes = pd.Series(code_array[np.asarray(valid_date)])
    date_index = date_index[valid_date]
    raw = raw[valid_date]

    n_raw = int(np.isfinite(raw).sum())
    sentinel = _sentinel_mask(raw)
    n_sentinel = int(sentinel.sum())
    remaining = raw.copy()
    remaining[sentinel] = np.nan
    suspect_kelvin = _kelvin_like(remaining)
    out_of_range = _out_of_range_mask(remaining)
    n_out_of_range = int(out_of_range.sum())
    remaining[out_of_range] = np.nan

    approval_codes_absent = codes is None
    n_provisional_dropped = 0
    estimated_approved = False
    ice_affected = False
    if codes is not None:
        keep, estimated, ice = _classify_codes(codes, len(remaining))
        provisional = np.isfinite(remaining) & ~keep
        n_provisional_dropped = int(provisional.sum())
        remaining[provisional] = np.nan
        estimated_approved = bool((keep & estimated).any())
        ice_affected = bool(ice.any())

    kept = np.isfinite(remaining)
    kept_dates = date_index[kept]
    kept_values = remaining[kept]
    n_constant_run_days = _count_constant_run_days(kept_dates, kept_values)
    n_jump = _count_jumps(kept_dates, kept_values)
    qualified_years = _qualified_years(kept_dates)
    verdict = _verdict(
        n_raw=n_raw,
        n_sentinel=n_sentinel,
        n_out_of_range=n_out_of_range,
        n_constant_run_days=n_constant_run_days,
        n_jump=n_jump,
        estimated_approved=estimated_approved,
        ice_affected=ice_affected,
        suspect_kelvin=suspect_kelvin,
    )
    return {
        "site_id": str(site_id),
        "n_raw": n_raw,
        "n_sentinel": n_sentinel,
        "n_out_of_range": n_out_of_range,
        "n_provisional_dropped": n_provisional_dropped,
        "n_constant_run_days": n_constant_run_days,
        "n_jump": n_jump,
        "qualified_years": qualified_years,
        "verdict": verdict,
        "notes": _notes(
            approval_codes_absent=approval_codes_absent,
            n_constant_run_days=n_constant_run_days,
            n_jump=n_jump,
            n_out_of_range=n_out_of_range,
            estimated_approved=estimated_approved,
            ice_affected=ice_affected,
            suspect_kelvin=suspect_kelvin,
        ),
    }


def _match_column(columns: Sequence[Any], aliases: Sequence[str]) -> str | None:
    lowered = {str(name).strip().lower(): name for name in columns}
    for alias in aliases:
        if alias.lower() in lowered:
            return str(lowered[alias.lower()])
    return None


def qc_long_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """QC a long table with date, site_id, value, and optional approval/qual code."""

    if frame.empty:
        return pd.DataFrame(columns=list(REPORT_COLUMNS))
    date_col = _match_column(frame.columns, DATE_COLUMN_ALIASES)
    site_col = _match_column(frame.columns, SITE_COLUMN_ALIASES)
    value_col = _match_column(frame.columns, VALUE_COLUMN_ALIASES)
    qual_col = _match_column(frame.columns, QUALIFIER_COLUMN_ALIASES)
    status_col = _match_column(frame.columns, APPROVAL_STATUS_COLUMN_ALIASES)
    if date_col is None or site_col is None or value_col is None:
        raise ValueError(
            "long ingest table needs date, site_id, and value columns "
            f"(got {list(frame.columns)})"
        )
    rows = []
    for site_id, group in frame.groupby(frame[site_col].map(lambda item: str(item)), sort=False):
        codes = _combined_approval_codes(group, qual_col, status_col)
        rows.append(
            qc_station_series(
                group[date_col],
                group[value_col],
                site_id=str(site_id),
                approval_codes=codes,
            )
        )
    return pd.DataFrame(rows, columns=list(REPORT_COLUMNS))


def qc_wide_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """QC a wide daily matrix (date column or index plus one column per site)."""

    if frame.empty:
        return pd.DataFrame(columns=list(REPORT_COLUMNS))
    working = frame.copy()
    date_col = _match_column(working.columns, DATE_COLUMN_ALIASES)
    if date_col is not None:
        dates = working[date_col]
        site_columns = [name for name in working.columns if name != date_col]
    else:
        dates = working.index
        site_columns = list(working.columns)
    rows = []
    for column in site_columns:
        rows.append(
            qc_station_series(
                dates,
                working[column],
                site_id=str(column),
                approval_codes=None,
            )
        )
    return pd.DataFrame(rows, columns=list(REPORT_COLUMNS))


def write_ingest_qc_report(
    frame: pd.DataFrame,
    path: str | Path,
) -> Path:
    """Write one row per station to ``ingest_qc_report.csv`` (or the given path)."""

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    report = pd.DataFrame(frame).copy()
    for column in REPORT_COLUMNS:
        if column not in report:
            report[column] = pd.NA
    report = report.loc[:, list(REPORT_COLUMNS)]
    report.to_csv(dest, index=False)
    return dest


def ingest_qc_report(
    frame: pd.DataFrame,
    *,
    layout: str = "auto",
) -> pd.DataFrame:
    """Dispatch long vs wide ingest tables."""

    if layout == "wide":
        return qc_wide_frame(frame)
    if layout == "long":
        return qc_long_frame(frame)
    site_col = _match_column(frame.columns, SITE_COLUMN_ALIASES)
    value_col = _match_column(frame.columns, VALUE_COLUMN_ALIASES)
    if site_col is not None and value_col is not None:
        return qc_long_frame(frame)
    return qc_wide_frame(frame)


__all__ = [
    "APPROVAL_COLUMN_ALIASES",
    "APPROVAL_STATUS_COLUMN_ALIASES",
    "CONSTANT_RUN_MAX_OK_DAYS",
    "JUMP_THRESHOLD_C",
    "MIN_EVALUABLE_SITE_YEAR_DAYS",
    "OUT_OF_RANGE_REJECT_FRACTION",
    "PHYSICAL_MAX_C",
    "PHYSICAL_MIN_C",
    "QUALIFIER_COLUMN_ALIASES",
    "REPORT_COLUMNS",
    "VERDICT_ACCEPTED",
    "VERDICT_ACCEPTED_WITH_FLAGS",
    "VERDICT_REJECTED_OUT_OF_RANGE",
    "VERDICT_REJECTED_SENTINEL",
    "ingest_qc_report",
    "is_nwis_sentinel_value",
    "qc_long_frame",
    "qc_station_series",
    "qc_wide_frame",
    "write_ingest_qc_report",
]
