#!/usr/bin/env python3
"""Generate fixed validation/test artificial-mask libraries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stream_recoverability.masks import (  # noqa: E402
    generate_async_mask,
    generate_block_mask,
    generate_multiblock_mask,
    generate_network_outage_mask,
    generate_point_mask,
    generate_station_outage_mask,
    save_mask_library,
)


DEFAULT_CONFIG: dict[str, Any] = {
    "splits": {
        "validation": {"seeds": list(range(101, 121))},
        "test": {"seeds": list(range(101, 121))},
    },
    "scenarios": [
        {
            "type": "point",
            "stations": "each",
            "variables": ["T"],
            "missing_rate": 0.30,
            "synchronized": True,
        },
        {"type": "block", "stations": "each", "variables": ["T"], "length": 30},
        {"type": "block", "stations": "each", "variables": ["T"], "length": 90},
    ],
}


VARIABLE_ALIASES = {
    "T": ("T", "WTEMP", "WATER_TEMPERATURE"),
    "F": ("F", "FLOW"),
    "L": ("L", "WLEVEL", "WATER_LEVEL"),
}


def _load_eligible_long(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, list[str], list[str], np.ndarray]:
    frame = pd.read_parquet(path)
    required = {"date", "station_id", "variable", "quality_approved", "split"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    frame = frame.loc[:, list(required)].copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    if frame.duplicated(["date", "station_id", "variable"]).any():
        raise ValueError("daily_long contains duplicate date/station/variable rows")
    if frame["quality_approved"].isna().any():
        raise ValueError("quality_approved must not contain missing values")

    dates = np.sort(frame["date"].unique()).astype("datetime64[D]")
    station_ids = [str(value) for value in pd.unique(frame["station_id"])]
    variable_names = [str(value) for value in pd.unique(frame["variable"])]
    full_columns = pd.MultiIndex.from_product(
        [station_ids, variable_names], names=["station_id", "variable"]
    )
    wide = frame.pivot(
        index="date", columns=["station_id", "variable"], values="quality_approved"
    )
    wide = wide.reindex(index=pd.to_datetime(dates), columns=full_columns, fill_value=False)
    eligible = wide.fillna(False).to_numpy(dtype=bool).reshape(
        len(dates), len(station_ids), len(variable_names)
    )

    split_counts = frame.groupby("date", observed=True)["split"].nunique(dropna=False)
    if (split_counts > 1).any():
        raise ValueError("one date is assigned to multiple splits")
    split_by_date = (
        frame.drop_duplicates("date")
        .set_index("date")["split"]
        .reindex(pd.to_datetime(dates))
        .astype(str)
        .to_numpy()
    )
    return eligible, dates, station_ids, variable_names, split_by_date


def _resolve_variables(requested: list[str], available: list[str]) -> list[int]:
    upper_to_index = {value.upper(): index for index, value in enumerate(available)}
    result: list[int] = []
    for name in requested:
        candidates = VARIABLE_ALIASES.get(str(name).upper(), (str(name),))
        match = next(
            (upper_to_index[candidate.upper()] for candidate in candidates if candidate.upper() in upper_to_index),
            None,
        )
        if match is None:
            raise ValueError(f"variable {name!r} is not present; available: {available}")
        result.append(match)
    return result


def _station_groups(spec: Any, station_ids: list[str]) -> list[list[int]]:
    if spec == "each" or spec is None:
        return [[index] for index in range(len(station_ids))]
    if spec == "all":
        return [list(range(len(station_ids)))]
    if not isinstance(spec, list) or not spec:
        raise ValueError("stations must be 'each', 'all', or a non-empty list")
    raw_groups = spec if isinstance(spec[0], list) else [spec]
    lookup = {name: index for index, name in enumerate(station_ids)}
    try:
        return [[lookup[str(name)] for name in group] for group in raw_groups]
    except KeyError as error:
        raise ValueError(f"unknown station: {error.args[0]}") from error


def _generate_scenario(
    scenario: dict[str, Any],
    eligible: np.ndarray,
    dates: np.ndarray,
    station_ids: list[str],
    variable_names: list[str],
    station_group: list[int],
    seed: int,
    split: str,
):
    kind = str(scenario["type"]).strip().lower().replace("-", "_")
    variables = _resolve_variables(
        [str(value) for value in scenario.get("variables", variable_names)],
        variable_names,
    )
    common = {
        "seed": seed,
        "dates": dates,
        "station_ids": station_ids,
        "variable_names": variable_names,
        "split": split,
    }
    if kind == "point":
        common.pop("dates")
        return generate_point_mask(
            eligible,
            float(scenario["missing_rate"]),
            station_indices=station_group,
            variable_indices=variables,
            synchronized=bool(scenario.get("synchronized", True)),
            **common,
        )
    if kind == "block":
        return generate_block_mask(
            eligible,
            int(scenario["length"]),
            station_indices=station_group,
            variable_indices=variables,
            season=scenario.get("season"),
            month=scenario.get("month"),
            context=int(scenario.get("context", 0)),
            **common,
        )
    if kind == "multiblock":
        return generate_multiblock_mask(
            eligible,
            int(scenario["total_budget"]),
            segment_lengths=scenario.get("segment_lengths"),
            minimum_gap=int(scenario.get("minimum_gap", 30)),
            station_indices=station_group,
            variable_indices=variables,
            context=int(scenario.get("context", 0)),
            **common,
        )
    if kind == "station_outage":
        if len(station_group) != 1:
            raise ValueError("station_outage scenarios must select one station at a time")
        return generate_station_outage_mask(
            eligible,
            station_group[0],
            int(scenario["length"]),
            mode=str(scenario.get("mode", "hydro-only")),
            **common,
        )
    if kind == "network_outage":
        return generate_network_outage_mask(
            eligible,
            station_group,
            int(scenario["length"]),
            variable_indices=variables,
            **common,
        )
    if kind == "async":
        return generate_async_mask(
            eligible,
            int(scenario["length"]),
            float(scenario["overlap_ratio"]),
            station_indices=station_group,
            variable_indices=variables,
            axis=str(scenario.get("axis", "station")),
            **common,
        )
    raise ValueError(f"unsupported mask type: {scenario['type']!r}")


def generate_libraries(input_path: Path, output_root: Path, config: dict[str, Any]) -> None:
    eligible, dates, station_ids, variable_names, split_by_date = _load_eligible_long(
        input_path
    )
    scenarios = config.get("scenarios")
    splits = config.get("splits")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("config.scenarios must be a non-empty list")
    if not isinstance(splits, dict) or not splits:
        raise ValueError("config.splits must be a non-empty mapping")

    for split, split_config in splits.items():
        split_selector = split_by_date == str(split)
        if not split_selector.any():
            raise ValueError(f"input contains no dates for split {split!r}")
        split_eligible = eligible & split_selector[:, None, None]
        default_seeds = split_config.get("seeds", [])
        generated = []
        for scenario in scenarios:
            seeds = scenario.get("seeds", default_seeds)
            if not seeds:
                raise ValueError(f"no seeds configured for split {split!r}")
            for station_group in _station_groups(scenario.get("stations"), station_ids):
                for seed in seeds:
                    generated.append(
                        _generate_scenario(
                            scenario,
                            split_eligible,
                            dates,
                            station_ids,
                            variable_names,
                            station_group,
                            int(seed),
                            str(split),
                        )
                    )
        save_mask_library(
            generated,
            output_root / str(split),
            dates=dates,
            station_ids=station_ids,
            variable_names=variable_names,
        )
        print(f"saved {len(generated)} fixed masks to {output_root / str(split)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data/processed/daily_long.parquet",
        help="processed daily_long.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "masks",
        help="output root containing validation/ and test/",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="optional YAML with splits and scenarios; defaults to T point-30/block-30/block-90",
    )
    args = parser.parse_args()
    config = DEFAULT_CONFIG
    if args.config is not None:
        loaded = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("mask config must be a YAML mapping")
        config = loaded
    generate_libraries(args.input, args.output, config)


if __name__ == "__main__":
    main()
