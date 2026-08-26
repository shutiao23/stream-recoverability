#!/usr/bin/env python3
"""Freeze open-role T2 outage geometry; never read sealed or outcome columns."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.frozen_outage_geometry import (
    build_adversarial_catalog,
    build_binding_manifest,
    build_natural_outage_catalog,
    load_open_role_availability,
    write_frozen_geometry_artifacts,
)

OPEN_ROLE = ROOT / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
OUTPUT = ROOT / "results/framework/t2_outage_geometry_v1"


def main() -> None:
    availability, source_audit = load_open_role_availability(OPEN_ROLE)
    natural = build_natural_outage_catalog(availability)
    adversarial = build_adversarial_catalog(availability)
    manifest = build_binding_manifest(availability, natural, adversarial, source_audit)
    manifest = write_frozen_geometry_artifacts(OUTPUT, natural, adversarial, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
