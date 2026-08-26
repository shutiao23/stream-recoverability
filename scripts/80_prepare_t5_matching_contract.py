#!/usr/bin/env python3
"""Prepare the outcome-blind v9.1 T5 station pair plan and attrition audit."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.regulation_panel import (
    load_freeze,
    load_gages_ii,
    load_gages_ii_bfi,
)
from stream_recoverability.experiments.t5_matching_contract import (
    build_station_covariates,
    collapse_predictor_rosters,
    make_pair_attrition,
    make_pair_plan,
    matching_readiness,
)

DESIGN = ROOT / "configs/design_freeze_v9.yaml"
PREDICTORS = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v1/train_only_predictors/"
    "train_only_predictors.csv"
)
GAGES_FREEZE = ROOT / "configs/regulation_panel_freeze_v1.yaml"
GAGES_CACHE = ROOT / "data/cache/regulation_panel_v1"
BFI_ARCHIVE = GAGES_CACHE / "basinchar_and_report_sept_2011.zip"
STATIONS = ROOT / "results/framework/public_catalog/usgs_daily_temperature_series.csv"
SPLIT = ROOT / "results/framework/public_catalog/catalog_v3_split_table.csv"
NLDI_CACHE = ROOT / "results/framework/public_catalog/nldi_cache"
OUTPUT = ROOT / "results/framework/t5_matching_contract_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_csv(frame: pd.DataFrame, path: Path) -> str:
    frame.to_csv(path, index=False)
    return _sha256(path)


def _nldi_cache_index(predictors: pd.DataFrame) -> pd.DataFrame:
    targets = collapse_predictor_rosters(predictors)["station_id"].astype(str)
    rows = []
    for target in sorted(set(targets)):
        for direction in ("UM", "DM"):
            path = NLDI_CACHE / f"{target}_{direction}_200.json"
            if path.is_file():
                rows.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "sha256": _sha256(path),
                    }
                )
    return pd.DataFrame(rows, columns=["path", "sha256"])


def main() -> None:
    design = yaml.safe_load(DESIGN.read_text(encoding="utf-8"))
    predictors = pd.read_csv(
        PREDICTORS, dtype={"network_id": str, "station_id": str}
    )
    gages_freeze = load_freeze(GAGES_FREEZE)
    gages, loaded_archive = load_gages_ii(
        gages_freeze, GAGES_CACHE, offline=True
    )
    if loaded_archive != BFI_ARCHIVE:
        raise RuntimeError("GAGES-II attribute and BFI loaders resolved different archives")
    bfi = load_gages_ii_bfi(
        gages_freeze, GAGES_CACHE, offline=True
    )
    stations = pd.read_csv(STATIONS, dtype={"site_id": str, "huc": str})
    split = pd.read_csv(SPLIT, dtype={"network_id": str, "role": str})
    covariates, attrition = build_station_covariates(
        predictors,
        gages=gages,
        bfi=bfi,
        station_catalog=stations,
        split_catalog=split,
        nldi_cache_dir=NLDI_CACHE,
    )
    pairs = make_pair_plan(covariates)
    pair_attrition = make_pair_attrition(covariates, pairs)
    nldi_index = _nldi_cache_index(predictors)
    factors = design.get("t5_confound_control", {}).get("matching_factors", [])
    manifest = matching_readiness(
        covariates,
        attrition,
        pairs,
        matching_factors=factors,
        pair_attrition=pair_attrition,
        input_paths={
            "design_freeze": DESIGN,
            "train_only_predictors": PREDICTORS,
            "gages_ii_archive": BFI_ARCHIVE,
            "station_catalog": STATIONS,
            "catalog_v3_split": SPLIT,
        },
    )
    # Keep the serialized paths portable while reading identities by absolute path.
    manifest["input_identities"] = {
        name: {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}
        for name, path in {
            "catalog_v3_split": SPLIT,
            "design_freeze": DESIGN,
            "gages_ii_archive": BFI_ARCHIVE,
            "station_catalog": STATIONS,
            "train_only_predictors": PREDICTORS,
        }.items()
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest["artifacts"] = {
        "station_covariates": {
            "path": "station_covariates.csv",
            "sha256": _write_csv(covariates, OUTPUT / "station_covariates.csv"),
        },
        "station_attrition": {
            "path": "station_attrition.csv",
            "sha256": _write_csv(attrition, OUTPUT / "station_attrition.csv"),
        },
        "pair_plan": {
            "path": "pair_plan.csv",
            "sha256": _write_csv(pairs, OUTPUT / "pair_plan.csv"),
        },
        "pair_attrition": {
            "path": "pair_attrition.csv",
            "sha256": _write_csv(pair_attrition, OUTPUT / "pair_attrition.csv"),
        },
        "nldi_cache_index": {
            "path": "nldi_cache_index.csv",
            "sha256": _write_csv(nldi_index, OUTPUT / "nldi_cache_index.csv"),
            "n_files": len(nldi_index),
        },
    }
    manifest_path = OUTPUT / "readiness_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
