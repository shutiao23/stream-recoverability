#!/usr/bin/env python3
"""Acquire the selected Hilltop cohort and apply the local measurement plan."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import time
from urllib.parse import quote, urlencode
import pandas as pd
import requests
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.independent import (
    load_acquisition_plan,
)
from stream_recoverability.experiments.tr_revision.native_temperature import (
    native_series,
    strict_daily_mean,
)

STUDY = T.ROOT / "results/wrr_review_completion_20261024/independent_study"
ENDPOINT = "https://hilltop.gw.govt.nz/Data.hts"
QC_SPEC = {
    "accepted_quality_codes": [600],
    "daily_completeness": 1.0,
    "cadence": "monthly timestamp mode up to 60 minutes, shorter tie, must divide 24 hours",
    "aggregation": "mean of a full regular native day; no interpolation or synthetic records",
    "native_clock": "NZST fixed UTC+12",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--study", type=Path, default=STUDY)
    p.add_argument("--acquire", action="store_true")
    p.add_argument(
        "--refresh",
        action="store_true",
        help="recompute daily means from cached native observations",
    )
    a = p.parse_args()
    status_path = a.study / "public_registration_status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    plan = load_acquisition_plan(a.study)
    if not a.acquire:
        print("Measurement plan loaded.")
        return 0
    roster = pd.read_csv(
        a.study / plan["metadata_roster_file"],
        dtype={"station_id": str, "station_key": str, "independence_group": str},
    )
    required = {
        "site",
        "station_id",
        "station_key",
        "independence_group",
        "measurement",
        "from",
        "to",
    }
    if required - set(roster) or roster.empty:
        raise RuntimeError("Acquisition roster is incomplete")
    receipt_path = a.study / "acquisition_receipt.json"
    receipt = (
        json.loads(receipt_path.read_text())
        if receipt_path.exists()
        else {
            "registration_id": status.get("registration_id"),
            "first_temperature_request_utc": None,
            "native_daily_qc_passed": False,
            "requests": [],
            "daily_files": [],
        }
    )
    directory = a.study / "acquired"
    directory.mkdir(exist_ok=True)

    session = requests.Session()

    def fetch(row, kind, start, end):
        key = f"{row.station_id}__{kind}__{start[:10]}__{end[:10]}"
        path = directory / (key + ".xml.gz")
        provenance = path.with_suffix(".request.json")
        if path.exists():
            return gzip.decompress(path.read_bytes())
        url = (
            plan["endpoint"]
            + "?"
            + urlencode(
                {
                    "Service": "Hilltop",
                    "Request": "GetData",
                    "Site": row.site,
                    "Measurement": row.measurement,
                    "TSType": kind,
                    "From": start,
                    "To": end,
                },
                quote_via=quote,
            )
        )
        stamp = datetime.now(timezone.utc).isoformat()
        if receipt["first_temperature_request_utc"] is None:
            receipt["first_temperature_request_utc"] = stamp
            T.write_json(receipt_path, receipt)
            status["water_temperature_values_requested"] = True
            status["first_temperature_request_utc"] = stamp
            T.write_json(a.study / "public_registration_status.json", status)
        response = session.get(url, timeout=180)
        response.raise_for_status()
        native_series(response.content, site=row.site, series_type=kind)
        path.write_bytes(gzip.compress(response.content))
        record = {"requested_utc": stamp, "url": url, "bytes": path.stat().st_size}
        T.write_json(provenance, record)
        receipt["requests"].append(record)
        T.write_json(receipt_path, receipt)
        time.sleep(0.5)
        return response.content

    cutoff = pd.Timestamp(plan["observation_end_exclusive"])
    for _, row in roster.sort_values("station_key").iterrows():
        daily_path = directory / (str(row.station_id) + "__daily.csv")
        if (
            not a.refresh
            and daily_path.exists()
            and any(
                item["station_key"] == row.station_key
                for item in receipt["daily_files"]
            )
        ):
            print(f"{row.site}: reusing observed daily means", flush=True)
            continue
        try:
            beginning = pd.Timestamp(row["from"])
            end = min(pd.Timestamp(row["to"]), cutoff)
            if end.tzinfo is not None:
                raise ValueError(
                    "Use native calendar strings for the requested date range"
                )
            quality = native_series(
                fetch(row, "StdQualSeries", "1900-01-01T00:00:00", end.isoformat()),
                site=row.site,
                series_type="StdQualSeries",
            )
            years = pd.date_range(f"{beginning.year}-01-01", end, freq="YS")
            chunks = []
            for start in years:
                stop = min(start + pd.offsets.YearBegin(1), end)
                if stop <= start:
                    continue
                chunks.append(
                    native_series(
                        fetch(row, "StdSeries", start.isoformat(), stop.isoformat()),
                        site=row.site,
                        series_type="StdSeries",
                    )
                )
            if not chunks:
                continue
            raw = pd.concat(chunks).sort_index()
            raw = raw.groupby(level=0).agg(
                lambda s: s.iloc[0] if len(s.unique()) == 1 else float("nan")
            )
            daily = strict_daily_mean(
                raw,
                quality,
                accepted_codes=tuple(
                    plan["qc_specification"]["accepted_quality_codes"]
                ),
                start=beginning.normalize().isoformat(),
                end_exclusive=end.ceil("D").isoformat(),
            )
            path = directory / (str(row.station_id) + "__daily.csv")
            daily.to_csv(path, index=False)
            receipt["daily_files"] = [
                f for f in receipt["daily_files"] if f["station_key"] != row.station_key
            ]
            receipt["daily_files"].append(
                {
                    "station_key": row.station_key,
                    "file": str(path.relative_to(a.study)),
                    "accepted_days": int(daily.complete_native_day.sum()),
                    "n_days": len(daily),
                }
            )
            receipt.get("unavailable", {}).pop(row.station_key, None)
            T.write_json(receipt_path, receipt)
            print(
                f"{row.site}: {int(daily.complete_native_day.sum())}/{len(daily)} quality-complete native days",
                flush=True,
            )

        except (requests.RequestException, ValueError) as error:
            receipt.setdefault("unavailable", {})[row.station_key] = str(error)
            T.write_json(receipt_path, receipt)
            print(f"{row.site}: unavailable: {error}", flush=True)
    receipt["native_daily_qc_passed"] = True
    receipt["qc_specification"] = plan["qc_specification"]
    receipt["qc_interpretation"] = (
        "Fixed procedure applied, not all observations accepted and not proof of measurement-error-free water temperature"
    )
    T.write_json(receipt_path, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
