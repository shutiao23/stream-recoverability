#!/usr/bin/env python3
"""Compare approved v2 legacy hydraulics with an existing v1 OGC network."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    compare_v2_to_v1_ogc,
)

V2_ROOT = (
    ROOT
    / "data_versions/global_network_corpus_v1/open_role_auxiliary_legacy_v2"
    / "failure_closure6"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-id", default="huc8_02040103")
    parser.add_argument("--v2-output-root", type=Path, default=V2_ROOT)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or (
        ROOT
        / "results/framework/t2_information_adapters_v2/legacy_vs_ogc"
        / args.network_id
    )
    result = compare_v2_to_v1_ogc(
        ROOT,
        args.v2_output_root,
        args.network_id,
        output,
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
