#!/usr/bin/env python3
"""F07: extend prior-access coverage to Parquet/JSON and site_id columns."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "f07_prior_access_formats"

EXCLUDE = (
    "wrr_submission_ready/p0_07_sealed_confirmation",
    "wrr_submission_ready/p0_07b_multi_agency_transport",
    "wrr_submission_ready/amendments",
    "raw_cache",
    "checkpoints",
    "checkpoints_v3",
    "online_checkpoints",
    "data_versions/",
    "failure_closure",
    "t2_recovery_benchmark",
    "t2_online_causal",
)
ID_FIELDS = ("station_id", "site_id", "usgs_site", "siteNo")
TEMP_HINTS = ("temperature", "wtemp", "water_temp", "metric_", "abserr_", "err_")


def skip(path: Path) -> bool:
    text = str(path).replace(str(ROOT) + "/", "")
    return any(part in text for part in EXCLUDE)


def classify(path: Path, fields: list[str]) -> str:
    names = " ".join(fields).lower() + " " + path.stem.lower()
    if any(token in names for token in ("loss", "prediction", "score", "abserr", "residual", "error")):
        return "outcome_bearing"
    if any(token in names for token in TEMP_HINTS):
        return "temperature_or_summary"
    return "metadata"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    parquet_paths = list(ROOT.glob("results/**/*.parquet"))
    json_paths = list(ROOT.glob("results/**/*.json")) + list(ROOT.glob("metadata/**/*.json"))
    for path in parquet_paths:
        if skip(path) or path.stat().st_size > 80_000_000:
            continue
        try:
            import pandas as pd

            frame = pd.read_parquet(path)
        except Exception:
            continue
        fields = [str(c) for c in frame.columns]
        hits = [c for c in fields if c in ID_FIELDS or c.lower() in ID_FIELDS]
        if not hits:
            continue
        n = 0
        for col in hits:
            n += int(frame[col].nunique(dropna=True))
        rows.append(
            {
                "artifact": str(path.relative_to(ROOT)),
                "format": "parquet",
                "id_fields": ",".join(hits),
                "n_unique_ids_sum": n,
                "use_class": classify(path, fields),
            }
        )
    for path in json_paths:
        if skip(path) or path.stat().st_size > 8_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not any(key in text for key in ID_FIELDS):
            continue
        rows.append(
            {
                "artifact": str(path.relative_to(ROOT)),
                "format": "json",
                "id_fields": "text_scan",
                "n_unique_ids_sum": "",
                "use_class": classify(path, [path.stem, text[:200]]),
            }
        )
    out = pd_frame(rows)
    out.to_csv(OUT / "artifacts.csv", index=False)
    summary = {
        "n_artifacts": int(len(out)),
        "by_format": out["format"].value_counts().to_dict() if len(out) else {},
        "by_class": out["use_class"].value_counts().to_dict() if len(out) else {},
        "note": (
            "Coverage expansion only. Presence of a station_id/site_id in an artifact "
            "is prior contact of some class; it does not prove outcome-based tuning. "
            "New confirmation must classify each hit against freeze time."
        ),
        "audit_was_csv_station_id_only": True,
        "csv_audit_script": "scripts/245_multi_agency_prior_access_audit.py",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


def pd_frame(rows):
    import pandas as pd

    return pd.DataFrame(rows)


if __name__ == "__main__":
    raise SystemExit(main())
