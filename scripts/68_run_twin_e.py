#!/usr/bin/env python3
"""Run the independent v9.1 Twin E known-Sigma gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.twin_e import run_twin_e, write_twin_e_artifacts

OUTPUT = ROOT / "results/framework/synthetic_v2/twin_e"


def main() -> None:
    result = run_twin_e()
    paths = write_twin_e_artifacts(result, OUTPUT)
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
