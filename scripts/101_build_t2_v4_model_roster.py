#!/usr/bin/env python3
"""Freeze the Tier-1 open-model roster against the post-T2 input binding."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_recovery_benchmark import TIER1_MODELS

DEFAULT_BINDING = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2/post_t2_input_binding.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2/model_roster.json"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_model_roster(
    *,
    binding_path: Path = DEFAULT_BINDING,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict:
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    if binding.get("status") != "complete":
        raise RuntimeError("post-T2 binding is not complete")
    roster = {
        "manifest_schema": "t2_v91_v4_open_model_roster_v1",
        "status": "model_selection_complete",
        "model_selection_complete": True,
        "post_selection_retuning": False,
        "sealed_outcomes_opened": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "purpose": "open_tier1_roster_frozen_to_post_t2_binding",
        "selected_models": list(TIER1_MODELS),
        "post_t2_input_binding_sha256": _sha256_file(binding_path),
        "post_t2_input_binding_path": str(
            binding_path.resolve().relative_to(ROOT.resolve())
        ),
        "development_binding": bool(binding.get("development_exclude_data_ineligible")),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(roster, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return roster


def main() -> None:
    roster = build_model_roster()
    print(json.dumps(roster, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
