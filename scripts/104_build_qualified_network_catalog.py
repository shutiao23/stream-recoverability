#!/usr/bin/env python3
"""Build network_catalog_v3_qualified.parquet from open-role and sealed QC manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CORPUS = ROOT / "data_versions/global_network_corpus_v1"
OUTPUT = CORPUS / "qualified_corpus_v1"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _eligible_from_qc(role: str) -> pd.DataFrame:
    path = (
        CORPUS
        / f"open_role_qc/failure_closure6/{role}/eligible_networks.csv"
    )
    if not path.is_file():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    frame["corpus_component"] = f"open_role_{role}"
    frame["qualification_mode"] = "failure_closure6"
    return frame


def build_qualified_catalog(repo_root: Path = ROOT) -> dict:
    open_frames = [
        _eligible_from_qc("development"),
        _eligible_from_qc("validation"),
    ]
    open_eligible = (
        pd.concat([f for f in open_frames if not f.empty], ignore_index=True)
        if any(not f.empty for f in open_frames)
        else pd.DataFrame()
    )
    if not open_eligible.empty:
        open_eligible = open_eligible.drop_duplicates("network_id")

    sealed_qc = _read_json(
        repo_root
        / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/sealed_qc_manifest.json"
    )
    sealed_eligible = pd.DataFrame()
    sealed_path = (
        repo_root
        / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/eligible_networks.csv"
    )
    if sealed_path.is_file():
        sealed_eligible = pd.read_csv(sealed_path)
        sealed_eligible["corpus_component"] = "sealed_t7_qc"
        sealed_eligible["qualification_mode"] = "sealed_evaluate_once"

    europe = _read_json(
        repo_root / "results/framework/public_rivers_europe/uk_ea_spatial_daily_manifest.json"
    )
    europe_count = int(europe.get("n_complete_enough", 0))

    frames = [f for f in (open_eligible, sealed_eligible) if not f.empty]
    qualified = (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    )
    if not qualified.empty and "network_id" in qualified.columns:
        qualified = qualified.drop_duplicates("network_id", keep="first")

    parquet_path = OUTPUT / "network_catalog_v3_qualified.parquet"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if qualified.empty:
        qualified = pd.DataFrame(
            columns=[
                "network_id",
                "provider",
                "corpus_component",
                "qualification_mode",
            ]
        )
    qualified.to_parquet(parquet_path, index=False)

    manifest = _read_json(OUTPUT / "qualified_corpus_manifest.json")
    return {
        "manifest_schema": "qualified_network_catalog_v1",
        "parquet_path": str(parquet_path.relative_to(repo_root)),
        "n_open_role_unique": int(len(open_eligible)),
        "n_sealed_eligible": int(len(sealed_eligible)),
        "n_europe_complete_enough": europe_count,
        "n_qualified_unique": int(len(qualified)),
        "network_ci_floor": int(manifest.get("network_ci_floor", 100)),
        "network_ci_floor_met": bool(manifest.get("network_ci_floor_met", False)),
        "formal_evidence": False,
        "purpose": "catalog_export_not_confirmatory",
    }


def main() -> None:
    report = build_qualified_catalog()
    meta_path = OUTPUT / "network_catalog_v3_qualified_manifest.json"
    meta_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
