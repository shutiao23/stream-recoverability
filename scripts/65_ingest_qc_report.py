#!/usr/bin/env python3
"""Station-level ingest QC for an already-downloaded public river wide CSV.

Does not download data. Default input is the Clearwater development fixture.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.ingest_qc import qc_wide_frame, write_ingest_qc_report

CLEARWATER_WIDE = ROOT / "results/framework/public_rivers/clearwater_river_huc17_daily_wide.csv"
OUTPUT = ROOT / "results/framework/public_rivers/ingest_qc_report_clearwater.csv"


def main(argv: list[str] | None = None) -> Path:
    args = list(sys.argv[1:] if argv is None else argv)
    source = Path(args[0]) if args else CLEARWATER_WIDE
    dest = Path(args[1]) if len(args) > 1 else OUTPUT
    if not source.is_file():
        raise FileNotFoundError(f"ingest QC source is missing (no download): {source}")
    wide = pd.read_csv(source)
    report = qc_wide_frame(wide)
    write_ingest_qc_report(report, dest)
    print(dest)
    print(report.to_string(index=False))
    return dest


if __name__ == "__main__":
    main()
