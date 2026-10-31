#!/usr/bin/env python3
"""P0-02/P0-08: build the peer-review input bundle for the current study.

The study reads 146 daily temperature panels plus one air-forcing table. Most of
those panels are derived from openly licensed provider services, but LUBW
reserves copyright on its raw values, so the panel set is not redistributed in
the public repository. This script assembles the exact bytes the analysis reads
into one archive with a manifest of its contents (paths and byte sizes), so the
authors can hand reviewers the same inputs through the journal's confidential
data channel.

It writes only under dist/ (gitignored) and results/wrr_submission_ready/.
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

READY = ROOT / "results" / "wrr_submission_ready"
MANIFEST = READY / "current_data_manifest.csv"
AIR = (
    ROOT
    / "results"
    / "development_v11"
    / "independent_air2stream_equivalent"
    / "daily_forcing.parquet"
)
OUT_DIR = ROOT / "dist"


def main() -> int:
    import pandas as pd

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT_DIR / "wrr_study_inputs_v1.tar.gz"))
    args = parser.parse_args()

    frame = pd.read_csv(MANIFEST)
    entries = []
    missing = []
    for row in frame.itertuples():
        path = ROOT / str(row.input_path)
        if not path.is_file():
            missing.append(str(row.input_path))
            continue
        entries.append(
            {
                "network_id": row.network_id,
                "provider": row.provider,
                "path": str(row.input_path),
                "bytes": path.stat().st_size,
            }
        )
    if missing:
        raise RuntimeError(f"{len(missing)} manifest inputs missing: {missing[:5]}")
    if not AIR.is_file():
        raise FileNotFoundError(AIR)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bundle_manifest = {
        "purpose": "peer-review input bundle for the WRR submission",
        "note": (
            "Contains the exact daily panels and air forcing the current study reads. "
            "LUBW values are included here for confidential peer review only because "
            "LUBW reserves copyright; they are not redistributed publicly."
        ),
        "n_panels": len(entries),
        "panels": entries,
        "air_forcing": {
            "path": str(AIR.relative_to(ROOT)),
            "bytes": AIR.stat().st_size,
        },
        "acquisition_routes": str(
            (READY / "current_data_acquisition.csv").relative_to(ROOT)
        ),
    }
    manifest_path = READY / "reviewer_input_bundle_manifest.json"
    manifest_path.write_text(
        json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n"
    )

    with tarfile.open(out, "w:gz") as tar:
        for entry in entries:
            tar.add(ROOT / entry["path"], arcname=entry["path"])
        tar.add(AIR, arcname=str(AIR.relative_to(ROOT)))
        tar.add(manifest_path, arcname=str(manifest_path.relative_to(ROOT)))

    print(
        json.dumps(
            {
                "bundle": str(out.relative_to(ROOT)),
                "bytes": out.stat().st_size,
                "n_panels": len(entries),
                "manifest": str(manifest_path.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
