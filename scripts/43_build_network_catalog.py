#!/usr/bin/env python3
"""Write the metadata-only multi-network catalog. No temperature outcomes."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.network_catalog import (
    catalog_frame,
    load_network_catalog,
    split_counts,
    validate_catalog,
)

OUTPUT = ROOT / "results/framework/network_catalog"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    document = load_network_catalog()
    violations = validate_catalog(document)
    frame = catalog_frame(document)
    frame.to_csv(OUTPUT / "network_catalog.csv", index=False)
    manifest = {
        "status": "complete" if not violations else "invalid",
        "catalog_id": document.get("catalog_id"),
        "sealed_outcomes_opened": False,
        "n_networks": int(len(frame)),
        "split_counts": split_counts(frame),
        "violations": violations,
        "temperature_outcomes_downloaded": False,
    }
    (OUTPUT / "catalog_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if violations:
        raise SystemExit("network catalog violations:\n" + "\n".join(violations))
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
