"""Shared paths, protocol settings and output helpers for the scientific revision."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
READY = ROOT / "results" / "wrr_submission_ready"
RUN = READY / "major_revision_20261020c"
DOCS = ROOT / "docs" / "reviews" / "wrr_major_revision_20261020c"
CONFIG = ROOT / "configs" / "wrr_revision_20261020c.json"


def source_cases(protocol_name: str, cohort: str = "admission") -> Path:
    if cohort == "admission":
        return (
            RUN
            / "r3_14_monitoring_replay"
            / protocol_name
            / "admission/cofailure_0/cases.parquet"
        )
    if cohort == "controlled":
        return RUN / "r3_03_representative_recovery" / protocol_name / "cases.parquet"
    raise ValueError(f"Unknown analysis cohort: {cohort}")


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def protocol() -> dict:
    return json.loads(CONFIG.read_text())


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
