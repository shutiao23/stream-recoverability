"""Repo-wide prior-use scan for SMHI station ids (read-only), mirroring scripts/245.

Reads every CSV under results/ and metadata/ carrying a station_id column, excluding
the ingest tree and run dirs, and reports which SMHI ids appear anywhere.
"""
from __future__ import annotations
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi/raw_cache"
CAT = json.loads((RAW / "parameter_4_catalog.json").read_text())
ids = {str(s["id"]) for s in CAT["station"]}

EXCLUDE = ("multi_agency_ingest", "/runs/", "raw_cache")
hits: dict[str, list[str]] = {}
scanned = 0
for root in (ROOT / "results", ROOT / "metadata"):
    if not root.is_dir():
        continue
    for path in root.rglob("*.csv"):
        text = str(path)
        if any(part in text for part in EXCLUDE):
            continue
        try:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or "station_id" not in reader.fieldnames:
                    continue
                scanned += 1
                found = set()
                for row in reader:
                    value = str(row.get("station_id") or "").strip()
                    for token in value.replace("|", ";").replace(",", ";").split(";"):
                        token = token.strip()
                        if token in ids:
                            found.add(token)
                if found:
                    hits[str(path.relative_to(ROOT))] = sorted(found)
        except (OSError, csv.Error, UnicodeDecodeError):
            continue

report = {
    "n_smhi_station_ids": len(ids),
    "n_csv_files_with_station_id_scanned": scanned,
    "n_files_with_overlap": len(hits),
    "overlaps": hits,
    "n_distinct_overlapping_ids": len({i for v in hits.values() for i in v}),
}
print(json.dumps(report, indent=2, ensure_ascii=False))
(ROOT / "scratch/smhi_prior_use_scan.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
