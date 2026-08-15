"""Shared constants for the three-station daily data set."""

from __future__ import annotations

from pathlib import Path

STATION_FILES = {
    "B1": "b1.csv",
    "S2": "s2.csv",
    "P3": "p3.csv",
}

RAW_VARIABLES = (
    "WTEMP",
    "WLEVEL",
    "FLOW",
    "TEMP",
    "WDSP",
    "PRCP",
    "RHMEAN",
    "DH",
)

DEFAULT_VARIABLE_SPECS = {
    "WTEMP": {
        "standard_name": "T",
        "raw_unit": "degC",
        "unit": "degC",
        "unit_conversion": "identity",
        "missing_codes": (),
    },
    "WLEVEL": {
        "standard_name": "L",
        "raw_unit": "unknown",
        "unit": "unknown",
        "unit_conversion": "identity",
        "missing_codes": (),
    },
    "FLOW": {
        "standard_name": "F",
        "raw_unit": "unknown",
        "unit": "unknown",
        "unit_conversion": "identity",
        "missing_codes": (),
    },
    "TEMP": {
        "standard_name": "Ta",
        "raw_unit": "degC",
        "unit": "degC",
        "unit_conversion": "identity",
        "missing_codes": (),
    },
    "WDSP": {
        "standard_name": "W",
        "raw_unit": "knot",
        "unit": "m/s",
        "unit_conversion": "knots_to_m_s",
        "missing_codes": (999.9,),
    },
    "PRCP": {
        "standard_name": "P",
        "raw_unit": "inch",
        "unit": "mm",
        "unit_conversion": "inches_to_mm",
        "missing_codes": (99.99,),
    },
    "RHMEAN": {
        "standard_name": "RH",
        "raw_unit": "%",
        "unit": "%",
        "unit_conversion": "identity",
        "missing_codes": (),
    },
    "DH": {
        "standard_name": "DH",
        "raw_unit": "unknown",
        "unit": "unknown",
        "unit_conversion": "identity",
        "missing_codes": (),
    },
}

SPLIT_RANGES = {
    "train": ("2006-01-01", "2015-12-31"),
    "validation": ("2016-01-01", "2017-12-31"),
    "test": ("2018-01-01", "2020-12-31"),
}

WINDOW_SIZES = (184, 368, 736)

DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_DATA_DICTIONARY = Path("metadata/data_dictionary.csv")
DEFAULT_AUDIT_DIR = Path("results/data_audit")
DEFAULT_PROCESSED_DIR = Path("data/processed")
