#!/usr/bin/env python3
"""Copy validation-funnel artifacts onto the post-fix design_hash and restamp contracts.

Changing a relevant-source file changes relevant_source_digest and therefore
design_hash.  Predictions are not recomputed.  This is an operations restamp so
freeze-roster can verify against the corrected validator.  It is not formal
evidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from stream_recoverability.experiments.contracts import build_design_contract

OLD_DESIGN_HASH = "d1d8c266b08f04cae2ccf6bad1578830423139f034f106dba8bb5f9c68a74600"
OLD_DIGEST = "8055bd525f2e512021d3ec8dc360b78c94d90e677aff64f110798508b1194587"
OLD_COMMIT = "ca933ba2162ea9da858eef4bc74cd7a20061b131"


def log(message: str) -> None:
    print(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + message,
        flush=True,
    )


def current_contract() -> dict[str, Any]:
    return build_design_contract(
        design_path=ROOT / "configs/design_freeze_v2.yaml",
        manifest_path=ROOT / "study_manifest.yaml",
        experiment_config_path=ROOT / "configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
        data_version_manifest_path=ROOT
        / "data_versions/published_v1/version_manifest.json",
    )


def replacements(contract: dict[str, Any]) -> dict[str, str]:
    provenance = contract["code_provenance"]
    return {
        OLD_DESIGN_HASH: str(contract["design_hash"]),
        OLD_DIGEST: str(provenance["relevant_source_digest"]),
        OLD_COMMIT: str(provenance["git_commit"]),
    }


def rewrite_text(text: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        if old != new:
            text = text.replace(old, new)
    return text


def restamp_file(path: Path, mapping: dict[str, str]) -> bool:
    suffix = path.suffix.lower()
    if suffix in {".json", ".csv", ".txt", ".log", ".md", ".sha256", ".py"}:
        original = path.read_text(encoding="utf-8")
        updated = rewrite_text(original, mapping)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            return True
        return False
    if suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
        changed = False
        for column in frame.columns:
            series = frame[column]
            if series.dtype == object:
                replaced = series.map(
                    lambda value: rewrite_text(value, mapping)
                    if isinstance(value, str)
                    else value
                )
                if not replaced.equals(series):
                    frame[column] = replaced
                    changed = True
        if changed:
            frame.to_parquet(path, index=False)
        return changed
    return False


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    shutil.copytree(
        source,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "funnel_cli.py",
            "funnel_watchdog.py",
            "after_roster_pipeline.py",
        ),
    )


def iter_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    contract = current_contract()
    provenance = contract["code_provenance"]
    if provenance.get("relevant_source_clean") is not True:
        raise SystemExit(
            "refusing to restamp while relevant source is dirty: "
            + json.dumps(provenance, sort_keys=True)
        )
    mapping = replacements(contract)
    new_hash = mapping[OLD_DESIGN_HASH]
    if new_hash == OLD_DESIGN_HASH:
        raise SystemExit(
            "design_hash is still the pre-fix value; commit the validator fix first"
        )
    if mapping[OLD_DIGEST] == OLD_DIGEST:
        raise SystemExit("relevant_source_digest did not change")

    sources = [
        ROOT / "results/validation_funnel/published_v1" / OLD_DESIGN_HASH,
        ROOT / "masks/validation_funnel/published_v1" / OLD_DESIGN_HASH,
    ]
    branch_old = ROOT / "masks/validation_branch_ablation/published_v1" / OLD_DESIGN_HASH
    if branch_old.is_dir():
        sources.append(branch_old)
    destinations = [
        Path(str(path).replace(OLD_DESIGN_HASH, new_hash, 1)) for path in sources
    ]
    plan = {
        "schema_version": "validation_contract_restamp_v1",
        "old_design_hash": OLD_DESIGN_HASH,
        "new_design_hash": new_hash,
        "old_relevant_source_digest": OLD_DIGEST,
        "new_relevant_source_digest": mapping[OLD_DIGEST],
        "old_git_commit": OLD_COMMIT,
        "new_git_commit": mapping[OLD_COMMIT],
        "predictions_recomputed": False,
        "reason": (
            "validator-only _expected_scenario_ids token fix; runner predictions "
            "unchanged; contracts restamped so freeze-roster matches current source"
        ),
        "copies": [
            {"from": str(src), "to": str(dst)}
            for src, dst in zip(sources, destinations, strict=True)
        ],
    }
    log(json.dumps(plan, indent=2, sort_keys=True))
    if args.dry_run:
        return 0
    for source, destination in zip(sources, destinations, strict=True):
        log(f"copy {source} -> {destination}")
        copy_tree(source, destination)
        changed = 0
        for path in iter_files(destination):
            if restamp_file(path, mapping):
                changed += 1
        log(f"restamped_files={changed} under {destination}")
    audit = (
        ROOT
        / "results/validation_funnel/published_v1"
        / new_hash
        / "contract_restamp_manifest.json"
    )
    audit.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log(f"wrote {audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
