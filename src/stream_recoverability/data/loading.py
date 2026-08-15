"""Read and clean the three station CSV files without losing raw values."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .schema import DEFAULT_VARIABLE_SPECS, RAW_VARIABLES, STATION_FILES

KNOT_TO_METRES_PER_SECOND = 0.5144444444444445
INCH_TO_MILLIMETRES = 25.4


def _parse_missing_codes(value: Any) -> tuple[float, ...]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ()
    if isinstance(value, (int, float, np.number)):
        return (float(value),)
    tokens = re.findall(r"[-+]?\d+(?:\.\d+)?", value)
    return tuple(float(token) for token in tokens)


def _conversion_factor(value: Any, raw_name: str) -> float:
    """Return a safe multiplicative factor from a data-dictionary entry."""

    default = DEFAULT_VARIABLE_SPECS[raw_name]["unit_conversion"]
    text = str(value).strip() if value is not None and not pd.isna(value) else str(default)
    normalized = re.sub(r"[^a-z0-9.]+", "_", text.lower()).strip("_")

    if normalized in {"", "identity", "none", "no_conversion", "1", "1.0"}:
        return 1.0
    if "knot" in normalized and ("m_s" in normalized or "metre" in normalized or "meter" in normalized):
        return KNOT_TO_METRES_PER_SECOND
    if "inch" in normalized and ("mm" in normalized or "millimet" in normalized):
        return INCH_TO_MILLIMETRES

    multiply = re.search(r"(?:\*|×|x|multiply(?:_by)?|factor)[_ ]*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if multiply:
        return float(multiply.group(1))
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
        return float(text)
    raise ValueError(f"Unsupported unit_conversion for {raw_name}: {text!r}")


def load_variable_specs(data_dictionary: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load variable metadata, filling absent entries with conservative defaults.

    The data dictionary is optional.  Its ``unit_conversion`` column is used when
    present.  No metadata file is created by this function.
    """

    specs = {name: dict(values) for name, values in DEFAULT_VARIABLE_SPECS.items()}
    if data_dictionary is None:
        return specs

    path = Path(data_dictionary)
    if not path.exists():
        return specs

    dictionary = pd.read_csv(path, skipinitialspace=True)
    if "raw_name" not in dictionary.columns:
        raise ValueError(f"{path} must contain a raw_name column")
    duplicates = dictionary["raw_name"].astype(str).str.strip().duplicated()
    if duplicates.any():
        names = dictionary.loc[duplicates, "raw_name"].tolist()
        raise ValueError(f"Duplicate raw_name entries in {path}: {names}")

    for _, row in dictionary.iterrows():
        raw_name = str(row["raw_name"]).strip()
        if raw_name not in specs:
            continue
        spec = specs[raw_name]
        for column in ("standard_name", "unit_conversion", "source"):
            if column in dictionary.columns and pd.notna(row[column]) and str(row[column]).strip():
                spec[column] = str(row[column]).strip()
        explicit_conversion = (
            "unit_conversion" in dictionary.columns
            and pd.notna(row["unit_conversion"])
            and bool(str(row["unit_conversion"]).strip())
        )
        if not explicit_conversion and "conversion_factor" in dictionary.columns and pd.notna(row["conversion_factor"]):
            spec["unit_conversion"] = str(row["conversion_factor"]).strip()

        raw_unit_columns = ("raw_unit", "original_unit")
        output_unit_columns = ("standard_unit", "target_unit")
        for column in raw_unit_columns:
            if column in dictionary.columns and pd.notna(row[column]) and str(row[column]).strip():
                spec["raw_unit"] = str(row[column]).strip()
                break
        for column in output_unit_columns:
            if column in dictionary.columns and pd.notna(row[column]) and str(row[column]).strip():
                spec["unit"] = str(row[column]).strip()
                break

        # A plain ``unit`` column describes the input unit unless the dictionary
        # provides explicit input/output unit columns.
        if "unit" in dictionary.columns and pd.notna(row["unit"]) and str(row["unit"]).strip():
            if not any(column in dictionary.columns for column in raw_unit_columns):
                spec["raw_unit"] = str(row["unit"]).strip()
            if _conversion_factor(spec["unit_conversion"], raw_name) == 1.0:
                spec["unit"] = str(row["unit"]).strip()

        if "missing_codes" in dictionary.columns:
            supplied = _parse_missing_codes(row["missing_codes"])
            # Confirmed project codes remain active even if metadata is partial.
            spec["missing_codes"] = tuple(dict.fromkeys((*spec["missing_codes"], *supplied)))

        # Validate early so an invalid metadata rule cannot silently alter data.
        _conversion_factor(spec["unit_conversion"], raw_name)
    return specs


def _code_mask(values: pd.Series, codes: tuple[float, ...]) -> pd.Series:
    mask = pd.Series(False, index=values.index)
    for code in codes:
        mask |= values.notna() & np.isclose(values.astype(float), code, rtol=0.0, atol=1e-9)
    return mask


def read_station_csv(
    path: str | Path,
    station_id: str,
    variable_specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Read one station into the canonical long format."""

    path = Path(path)
    specs = variable_specs or load_variable_specs()
    raw = pd.read_csv(path, skipinitialspace=True)
    required = {"DATE", *RAW_VARIABLES}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")

    dates = pd.to_datetime(raw["DATE"], errors="raise").dt.normalize()
    frames: list[pd.DataFrame] = []
    for raw_name in RAW_VARIABLES:
        original = pd.to_numeric(raw[raw_name], errors="coerce")
        invalid_numeric = raw[raw_name].notna() & original.isna()
        if invalid_numeric.any():
            rows = invalid_numeric[invalid_numeric].index[:5].tolist()
            raise ValueError(f"Non-numeric {raw_name} values in {path} at rows {rows}")

        spec = specs[raw_name]
        special_code = _code_mask(original, tuple(spec.get("missing_codes", ())))
        natural_observed = original.notna() & ~special_code
        cleaned = original.where(natural_observed)
        factor = _conversion_factor(spec.get("unit_conversion"), raw_name)

        frame = pd.DataFrame(
            {
                "date": dates,
                "station_id": station_id,
                "variable": str(spec["standard_name"]),
                "raw_name": raw_name,
                "raw_value": original.astype(float),
                "value": cleaned.astype(float) * factor,
                "raw_unit": str(spec.get("raw_unit", "unknown")),
                "unit": str(spec.get("unit", "unknown")),
                "natural_observed": natural_observed.astype(bool),
                "quality_approved": natural_observed.astype(bool),
                "qc_status": np.where(natural_observed, "observed_unflagged", "source_missing"),
                "source": str(spec.get("source", path.name)),
            }
        )
        frames.append(frame)

    return pd.concat(frames, ignore_index=True)


def load_stations(
    raw_dir: str | Path,
    data_dictionary: str | Path | None = None,
    station_files: Mapping[str, str] = STATION_FILES,
) -> pd.DataFrame:
    """Read B1, S2, and P3 (or an explicitly supplied station mapping)."""

    raw_dir = Path(raw_dir)
    specs = load_variable_specs(data_dictionary)
    frames = []
    for station_id, filename in station_files.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing raw station file: {path}")
        frames.append(read_station_csv(path, station_id, specs))
    return pd.concat(frames, ignore_index=True)
