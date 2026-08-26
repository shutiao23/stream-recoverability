#!/usr/bin/env python3
"""First-score runner for the commit-guarded v9.1 Twin E hold-out."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.twin_e import (
    run_locked_twin_e_holdout,
    write_locked_twin_e_holdout_artifacts,
)

LOCK = ROOT / "configs/twin_e_holdout_freeze_v1.yaml"
OUTPUT = ROOT / "results/framework/synthetic_v2/twin_e_holdout"


def main() -> None:
    result = run_locked_twin_e_holdout(LOCK)
    paths = write_locked_twin_e_holdout_artifacts(
        result,
        OUTPUT,
        lock_path=LOCK.relative_to(ROOT),
    )
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "artifacts": {name: str(path) for name, path in paths.items()},
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
