"""Shared loaders and small statistics for the 2026-10-20b attribution round.

The round answers the second simulated review of 2026-10-20.  Everything here is
read-only with respect to the earlier rounds: panels, thresholds and cross-fitted
scores are taken from ``major_revision_20261020`` and never rewritten.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

READY = ROOT / "results" / "wrr_submission_ready"
PREV = READY / "major_revision_20261020"
RUN = READY / "major_revision_20261020b"
ALIGNED = PREV / "p0_01_aligned_policy_admission"
REPLAY_CASES = PREV / "p0_03_real_calendar_adoption" / "replay_case_decisions.parquet"
REPLAY_RAW = (
    READY / "major_revision_20261014" / "p0_03_final_method_replay" / "replay_decisions.parquet"
)
CROSSED_PARQUET = READY / "amendments" / "position_length_paired" / "crossed_development_cases.parquet"
EXTERNAL_PARQUET = (
    READY / "p0_07_wave2_ingest" / "p0_07_wave2_confirmation" / "wave2_cases.parquet"
)


def development_parquet() -> Path:
    from stream_recoverability.experiments.v17_fitness.paths import STEP4_CEILING

    return STEP4_CEILING / "development_cases.parquet"


def load_script(name: str, path: Path):
    """Import a numbered script as a module (they are not on the package path)."""

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODELS: dict = {}


def load_311():
    """Scripts 301 and 311 bound exactly as ``330`` binds them, loaded lazily so
    that a process-pool worker can build them itself (a dynamically imported
    module object cannot be pickled across processes)."""

    if "m311" not in _MODELS:
        m301 = load_script("wrr301", ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py")
        m311 = load_script("wrr311", ROOT / "scripts" / "311_wrr_p0_02_frozen_risk_thresholds.py")
        m311.M301 = m301
        _MODELS.update(m301=m301, m311=m311)
    return _MODELS["m311"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - diagnostics only
        return "unknown"


def write_fingerprint(out_dir: Path, script: str, inputs: dict[str, Path], extra: dict | None = None):
    payload = {
        "script": script,
        "git_head": git_head(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "inputs": {
            name: {"path": str(Path(path).relative_to(ROOT)), "sha256": sha256_file(Path(path))}
            for name, path in inputs.items()
        },
    }
    if extra:
        payload.update(extra)
    (out_dir / "protocol_fingerprint.json").write_text(json.dumps(payload, indent=2, sort_keys=True))


def cluster_bootstrap(values_by_cluster, stat, *, draws: int = 2000, seed: int = 0):
    """Percentile interval for ``stat`` over whole clusters resampled with replacement.

    ``values_by_cluster`` is a list of per-cluster payloads; ``stat`` maps a list
    of payloads to a float.  The point estimate uses every cluster once.
    """

    n = len(values_by_cluster)
    point = float(stat(values_by_cluster))
    if n < 2:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(int(seed))
    out = np.empty(int(draws))
    for i in range(int(draws)):
        pick = rng.integers(0, n, n)
        out[i] = stat([values_by_cluster[j] for j in pick])
    finite = out[np.isfinite(out)]
    if finite.size == 0:
        return point, float("nan"), float("nan")
    return point, float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))
