#!/usr/bin/env python3
"""Backfill identical tail chunks while the canonical role evaluations run.

This only schedules script 390's existing deterministic sampler. It changes no
model, case, mask, draw budget, diffusion step, seed or reconstruction result.
"""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from joblib import Parallel, delayed

import wrr_r3_common as C

PROB = C.READY / "followup_20261021/probability_development"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


class InputsCaptured(Exception):
    pass


def capture(role):
    core = C.load_script("probability_input_backfill", C.ROOT / "scripts/385_wrr_probability_development.py")
    captured = {}
    class CaptureOnly:
        def load(self, path):
            pass
        def predict(self, data, n_sampling_times):
            if set(data) != {"X"} or n_sampling_times != 32:
                raise RuntimeError("Canonical inference contract changed")
            captured["X"] = data["X"]
            raise InputsCaptured
    core.model_instance = lambda name, threads: CaptureOnly()
    try:
        core.evaluate(role, 1)
    except InputsCaptured:
        return captured["X"]
    raise RuntimeError("Did not capture the unmodified canonical inputs")


def worker(*args):
    import importlib
    return importlib.import_module("390_wrr_developed_probability_system").sample_chunk(*args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    selected = json.loads((PROB / "selection.json").read_text())["selected"]
    roles = ("development", "calibration", "test")
    # Reuse the actual input-building implementation, stopping before inference
    # or any case-result write. No recovery outcome is used by this scheduler.
    inputs = {role: capture(role) for role in roles}
    count = max((len(values) + 3) // 4 for values in inputs.values())
    tasks = [(role, 4 * chunk) for chunk in range(count - 1, -1, -1) for role in roles
             if 4 * chunk < len(inputs[role]) and not (PROB / role / "sampling_chunks" / f"case_{4 * chunk:05d}.npz").exists()]
    C.write_json(PROB / "parallel_backfill_contract.json", run_record({"selection": PROB / "selection.json", "canonical_sampler": C.ROOT / "scripts/390_wrr_developed_probability_system.py", "canonical_inputs": C.ROOT / "scripts/385_wrr_probability_development.py"},
                 additional_workers_shared_across_roles=args.workers, threads_per_worker=1, canonical_role_workers_each=12,
                 model_or_statistical_budget_changed=False,
                 scheduling="descending tail chunks; canonical scheduler fills ascending; exact same chunk function and seed"))
    Parallel(n_jobs=args.workers, verbose=10)(delayed(worker)(selected, role, start, inputs[role][start:start + 4], 32) for role, start in tasks)
    C.write_json(PROB / "parallel_backfill_completed.json", {"scheduled_tasks": len(tasks), "statistical_inference_unchanged": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
