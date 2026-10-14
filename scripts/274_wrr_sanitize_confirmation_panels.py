#!/usr/bin/env python3
"""P0-02: sanitize already-ingested confirmation/transport daily panels.

Writes repaired copies under amendments/p0_02_sanitized_panels/ and a remap
manifest. Does not overwrite sealed input bytes. Complete-year eligibility must
be rebuilt from the sanitized copies before any rescoring.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "p0_02_sanitized_panels"
TEMP_MIN, TEMP_MAX = -5.0, 50.0
NODATA = -999999.0


_META_COLS = {
    "date",
    "quality_code",
    "station_id",
    "site_id",
    "network_id",
    "provider",
    "qualifier",
    "qualifiers",
}


def _temperature_columns(frame, date_col: str) -> list[str]:
    cols = [str(c) for c in frame.columns if str(c).strip().lower() != date_col]
    lower = {c: c.strip().lower() for c in cols}
    # Long-format: explicit temperature field(s).
    explicit = [c for c, key in lower.items() if "temperature" in key or key in {"value", "temp_c", "wtemp"}]
    if explicit:
        return explicit
    # Wide panel: every non-metadata column is a station series.
    return [c for c, key in lower.items() if key not in _META_COLS]


def sanitize_frame(frame, date_col: str = "date"):
    import pandas as pd

    out = frame.copy()
    stats = {"n_nodata": 0, "n_implausible": 0}
    for col in _temperature_columns(out, date_col):
        values = pd.to_numeric(out[col], errors="coerce")
        nodata = values.eq(NODATA)
        stats["n_nodata"] += int(nodata.sum())
        values = values.mask(nodata)
        implausible = values.notna() & ((values < TEMP_MIN) | (values > TEMP_MAX))
        stats["n_implausible"] += int(implausible.sum())
        values = values.mask(implausible)
        out[col] = values
    return out, stats


def main() -> int:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    sources += sorted((READY / "confirmation_ingest").glob("**/daily_wide_temperature.csv"))
    sources += sorted((READY / "multi_agency_ingest").glob("**/networks/*/daily_wide_temperature.csv"))
    sources += sorted((READY / "multi_agency_ingest").glob("**/networks_qc/*/daily_wide_temperature.csv"))
    sources += sorted((READY / "multi_agency_ingest").glob("**/station_daily/*.csv"))

    rows = []
    for src in sources:
        rel = src.relative_to(READY)
        dest = OUT / "panels" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.read_csv(src)
        date_col = "date" if "date" in frame.columns else frame.columns[0]
        cleaned, stats = sanitize_frame(frame, date_col=date_col)
        cleaned.to_csv(dest, index=False)
        rows.append(
            {
                "source": str(rel),
                "dest": str(dest.relative_to(ROOT)),
                **stats,
                "changed": bool(stats["n_nodata"] or stats["n_implausible"]),
            }
        )

    report = pd.DataFrame(rows)
    report.to_csv(OUT / "sanitize_manifest.csv", index=False)
    summary = {
        "n_files": int(len(report)),
        "n_files_changed": int(report["changed"].sum()) if len(report) else 0,
        "n_nodata_blanked": int(report["n_nodata"].sum()) if len(report) else 0,
        "n_implausible_blanked": int(report["n_implausible"].sum()) if len(report) else 0,
        "policy": "Copies only; sealed originals untouched; rebuild eligibility from dest paths",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
