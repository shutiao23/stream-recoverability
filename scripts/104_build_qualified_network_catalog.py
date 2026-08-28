#!/usr/bin/env python3
"""Build network_catalog_v3_qualified.parquet from open-role and sealed QC manifests."""

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

CORPUS = ROOT / "data_versions/global_network_corpus_v1"
OUTPUT = CORPUS / "qualified_corpus_v1"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_inventory(repo_root: Path) -> pd.DataFrame:
    """Return the frozen HUC8 and prospective FOEN candidate universe."""

    huc8 = yaml.safe_load(
        (repo_root / "configs/network_catalog_v3_split.yaml").read_text(
            encoding="utf-8"
        )
    )
    rows: list[dict[str, object]] = []
    for row in huc8["networks"]:
        rows.append(
            {
                "network_id": row["network_id"],
                "provider": "usgs_nwis",
                "locked_role": row["role"],
                "climate_band": row.get("climate_band") or "not_available",
                "size_tertile": row.get("size_tertile") or "not_available",
                "regulation_stratum": row.get("regulation_stratum")
                or "not_available",
                "n_catalog_stations": row.get("n_stations"),
            }
        )
    foen = yaml.safe_load(
        (repo_root / "configs/foen_prospective_split_v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    for row in foen["networks"]:
        rows.append(
            {
                "network_id": row["network_id"],
                "provider": "foen",
                "locked_role": row["role"],
                "climate_band": "not_available",
                "size_tertile": "not_available",
                "regulation_stratum": "not_available",
                "n_catalog_stations": len(row.get("station_ids") or []),
            }
        )
    candidates = pd.DataFrame(rows)
    if candidates["network_id"].duplicated().any():
        raise ValueError("candidate inventory contains duplicate network IDs")
    return candidates.sort_values(["provider", "network_id"]).reset_index(drop=True)


def _open_attrition(repo_root: Path) -> pd.DataFrame:
    frames = []
    for role in ("development", "validation"):
        path = (
            repo_root
            / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
            / role
            / "overlap_attrition.csv"
        )
        if path.is_file():
            frames.append(pd.read_csv(path))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _exclusion_reason(
    candidate: pd.Series,
    *,
    open_attrition: pd.DataFrame,
    sealed_attrition: pd.DataFrame,
) -> tuple[str, str]:
    role = str(candidate["locked_role"])
    network_id = str(candidate["network_id"])
    if role in {"historical", "never_sealed"}:
        return "role_assignment", f"locked_role_{role}_not_in_inference_corpus"
    if role in {"development", "validation"}:
        match = open_attrition.loc[open_attrition["network_id"].eq(network_id)]
        if match.empty:
            return "open_role_custody", "open_role_qc_record_missing"
        row = match.iloc[0]
        if int(row.get("n_qc_eligible_stations", 0)) < 3:
            return "open_role_qc", "fewer_than_3_qc_eligible_stations"
        return "open_role_overlap", "fewer_than_6_concurrent_qualified_years"
    if role == "sealed":
        match = sealed_attrition.loc[sealed_attrition["network_id"].eq(network_id)]
        if match.empty:
            return "sealed_qc", "sealed_qc_record_missing_or_not_eligible"
        return "sealed_qc", str(match.iloc[0]["reason"])
    return "role_assignment", f"unsupported_locked_role_{role}"


def _write_exclusions_and_balance(
    repo_root: Path, output: Path, qualified: pd.DataFrame
) -> dict[str, object]:
    candidates = _candidate_inventory(repo_root)
    open_attrition = _open_attrition(repo_root)
    sealed_attrition_path = (
        repo_root
        / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/network_attrition.csv"
    )
    sealed_attrition = (
        pd.read_csv(sealed_attrition_path)
        if sealed_attrition_path.is_file()
        else pd.DataFrame(columns=["network_id", "reason"])
    )
    qualified_ids = set(qualified["network_id"].astype(str))
    exclusion_rows = []
    for _, candidate in candidates.loc[
        ~candidates["network_id"].isin(qualified_ids)
    ].iterrows():
        stage, reason = _exclusion_reason(
            candidate,
            open_attrition=open_attrition,
            sealed_attrition=sealed_attrition,
        )
        exclusion_rows.append(
            {
                **candidate.to_dict(),
                "exclusion_stage": stage,
                "exclusion_reason": reason,
            }
        )
    exclusions = pd.DataFrame(exclusion_rows).sort_values(
        ["provider", "network_id"]
    )
    exclusions_path = output / "network_catalog_v3_exclusions.csv"
    exclusions.to_csv(exclusions_path, index=False)

    qualified_candidate = candidates.loc[
        candidates["network_id"].isin(qualified_ids)
    ].copy()
    balance_rows = []
    for dimension in (
        "provider",
        "locked_role",
        "climate_band",
        "size_tertile",
        "regulation_stratum",
    ):
        candidate_counts = candidates[dimension].value_counts(dropna=False)
        qualified_counts = qualified_candidate[dimension].value_counts(dropna=False)
        for level in sorted(str(value) for value in candidate_counts.index):
            candidate_count = int(candidate_counts.get(level, 0))
            qualified_count = int(qualified_counts.get(level, 0))
            balance_rows.append(
                {
                    "dimension": dimension,
                    "level": level,
                    "candidate_count": candidate_count,
                    "qualified_count": qualified_count,
                    "excluded_count": candidate_count - qualified_count,
                    "qualification_rate": (
                        qualified_count / candidate_count if candidate_count else None
                    ),
                }
            )
    balance = pd.DataFrame(balance_rows)
    balance_path = output / "network_catalog_v3_balance.csv"
    balance.to_csv(balance_path, index=False)
    return {
        "candidate_inventory_count": len(candidates),
        "excluded_count": len(exclusions),
        "candidate_qualified_count": len(qualified_candidate),
        "qualified_outside_huc8_candidates": len(qualified_ids - set(candidates["network_id"])),
        "exclusions_path": str(exclusions_path.relative_to(repo_root)),
        "exclusions_sha256": _sha256(exclusions_path),
        "balance_path": str(balance_path.relative_to(repo_root)),
        "balance_sha256": _sha256(balance_path),
        "balance_dimensions": sorted(balance["dimension"].unique().tolist()),
    }


def _eligible_from_qc(repo_root: Path, role: str) -> pd.DataFrame:
    """Reconstruct the open-role eligible inventory from canonical QC manifests.

    The QC pipeline writes one ``network_qc_manifest.json`` per network; it
    never wrote the role-level ``eligible_networks.csv`` path used by the first
    catalog exporter.  Reading the per-network manifests keeps the export tied
    to the actual ``overlap.complete_enough`` decision instead of silently
    returning an empty open-role catalog.
    """

    network_root = (
        repo_root
        / "data_versions/global_network_corpus_v1/open_role_qc"
        / "failure_closure6"
        / role
        / "networks"
    )
    rows: list[dict[str, object]] = []
    for path in sorted(network_root.glob("*/network_qc_manifest.json")):
        document = _read_json(path)
        overlap = document.get("overlap") or {}
        if overlap.get("complete_enough") is not True:
            continue
        rows.append(
            {
                "network_id": document.get("network_id") or path.parent.name,
                "provider": "usgs_nwis",
                "role": role,
                "corpus_component": f"open_role_{role}",
                "qualification_mode": "failure_closure6",
                "n_locked_stations": overlap.get("n_requested_stations"),
                "n_qc_accepted_stations": overlap.get("n_qc_eligible_stations"),
                "overlap_start": overlap.get("overlap_start"),
                "overlap_end": overlap.get("overlap_end"),
                "overlap_years": overlap.get("overlap_years"),
                "days_with_min_stations": overlap.get("days_with_min_stations"),
            }
        )
    return pd.DataFrame(rows)


def build_qualified_catalog(repo_root: Path = ROOT) -> dict:
    open_frames = [
        _eligible_from_qc(repo_root, "development"),
        _eligible_from_qc(repo_root, "validation"),
    ]
    open_eligible = (
        pd.concat([f for f in open_frames if not f.empty], ignore_index=True)
        if any(not f.empty for f in open_frames)
        else pd.DataFrame()
    )
    if not open_eligible.empty:
        open_eligible = open_eligible.drop_duplicates("network_id")

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

    output = repo_root / "data_versions/global_network_corpus_v1/qualified_corpus_v1"
    parquet_path = output / "network_catalog_v3_qualified.parquet"
    output.mkdir(parents=True, exist_ok=True)
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

    manifest = _read_json(output / "qualified_corpus_manifest.json")
    expected_total = int(manifest.get("qualified_total", len(qualified)))
    observed_total = len(qualified)
    if observed_total != expected_total:
        raise ValueError(
            "qualified catalog count does not match corpus manifest: "
            f"catalog={observed_total}, manifest={expected_total}"
        )
    provider_counts = {
        str(key): int(value)
        for key, value in qualified["provider"].value_counts().sort_index().items()
    }
    role_counts = {
        str(key): int(value)
        for key, value in qualified["corpus_component"]
        .value_counts()
        .sort_index()
        .items()
    }
    audit_outputs = _write_exclusions_and_balance(repo_root, output, qualified)
    return {
        "manifest_schema": "qualified_network_catalog_v1",
        "parquet_path": str(parquet_path.relative_to(repo_root)),
        "n_open_role_unique": len(open_eligible),
        "n_sealed_eligible": len(sealed_eligible),
        "n_europe_complete_enough": europe_count,
        "n_qualified_unique": observed_total,
        "corpus_manifest_qualified_total": expected_total,
        "count_matches_corpus_manifest": True,
        "provider_counts": provider_counts,
        "corpus_component_counts": role_counts,
        "audit_outputs": audit_outputs,
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
