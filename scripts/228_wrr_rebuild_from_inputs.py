#!/usr/bin/env python3
"""P0-02/P0-08 entry: rebuild current-study inputs from hashed daily panels.

Verifies ``current_data_manifest.csv`` hashes, optionally clears the panel
cache, and loads every study network once. Full case regeneration remains the
existing v17/v18 scripts; this entrypoint proves the study inputs are present
and match the sealed hashes before those scripts run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from stream_recoverability.experiments.v17_fitness.panel import load_network_panel
from stream_recoverability.experiments.wrr_submission_ready.run_identity import (
    run_fail_closed,
    sha256_file,
)

MANIFEST = ROOT / "results" / "wrr_submission_ready" / "current_data_manifest.csv"


def verify_and_load(directory: Path, manifest, *, clear_cache: bool) -> list[Path]:
    if clear_cache:
        load_network_panel.cache_clear()
    frame = pd.read_csv(MANIFEST)
    rows = []
    for row in frame.itertuples():
        path = ROOT / row.input_path
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256_file(path)
        if digest != row.sha256:
            raise RuntimeError(f"hash mismatch for {row.network_id}")
        panel = load_network_panel(str(row.network_id), str(row.source_root))
        rows.append(
            {
                "network_id": row.network_id,
                "n_days": int(len(panel)),
                "n_stations": int(panel.shape[1]),
                "sha256_ok": True,
            }
        )
    out = directory / "input_load_report.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    summary = {
        "n_networks": len(rows),
        "status": "inputs_verified_and_loaded",
        "next": [
            "python3 scripts/181_v17_cases.py",
            "python3 scripts/187_v17_confirm.py",
            "python3 scripts/210_v18_outage_seasonality.py",
        ],
    }
    summary_path = directory / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return [out, summary_path]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear-cache", action="store_true")
    args = parser.parse_args()
    run_fail_closed(
        "P0-02 verify hashed daily inputs",
        lambda d, m: verify_and_load(d, m, clear_cache=args.clear_cache),
        inputs=[MANIFEST],
    )
    print("ok: all study network daily panels match current_data_manifest.csv")


if __name__ == "__main__":
    main()
