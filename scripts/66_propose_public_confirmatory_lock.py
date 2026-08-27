#!/usr/bin/env python3
"""T7 metadata-only sealed assignment. Refuses until floors are met.

Does not open temperatures. Does not remap network_catalog_v1. Last-check
and burned rivers cannot enter the sealed list.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.public_confirmatory_lock import (
    propose_sealed_networks,
    write_lock_or_refuse,
)

V2 = ROOT / "results/framework/public_rivers_v2"
EUROPE = ROOT / "results/framework/public_rivers_europe"
LOCK = V2 / "confirmatory_once.lock.json"


def _rows_from_overlap(path: Path, continent: str) -> list[dict]:
    if not path.is_file():
        return []
    table = pd.read_csv(path)
    rows = []
    for row in table.itertuples(index=False):
        network_id = str(getattr(row, "network_id", ""))
        complete = bool(getattr(row, "complete_enough", False))
        rows.append(
            {
                "network_id": network_id,
                "continent": continent,
                "complete_enough": complete,
            }
        )
    return rows


def main() -> None:
    candidates = []
    candidates.extend(_rows_from_overlap(V2 / "overlap.csv", "north_america"))
    candidates.extend(_rows_from_overlap(EUROPE / "overlap.csv", "europe"))
    candidates.extend(_rows_from_overlap(EUROPE / "uk_ea_overlap.csv", "europe"))
    proposal = propose_sealed_networks(candidates)
    written = write_lock_or_refuse(proposal, path=LOCK)
    (V2 / "confirmatory_lock_attempt.json").write_text(
        json.dumps(written, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {key: written[key] for key in written if key != "rejected"},
        indent=2,
        default=str,
    ))


if __name__ == "__main__":
    main()
