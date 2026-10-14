#!/usr/bin/env python3
"""P0-02 deliverable: QC ledger tracing -999999, SMHI coding, HubEau homonyms, daily contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "p0_02_qc_ledger"
TEMP_MIN, TEMP_MAX = -5.0, 50.0
NODATA = -999999.0


def main() -> int:
    import numpy as np
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    # USGS confirmation panels
    usgs_root = READY / "confirmation_ingest"
    for csv_path in sorted(usgs_root.glob("**/daily_wide_temperature.csv")):
        panel = pd.read_csv(csv_path)
        date_col = "date" if "date" in panel.columns else panel.columns[0]
        for station in [c for c in panel.columns if c != date_col]:
            values = pd.to_numeric(panel[station], errors="coerce")
            n_nodata = int((values == NODATA).sum())
            finite = values[np.isfinite(values) & (values != NODATA)]
            n_implausible = int(((finite < TEMP_MIN) | (finite > TEMP_MAX)).sum())
            if n_nodata or n_implausible:
                rows.append(
                    {
                        "provider": "usgs",
                        "panel_path": str(csv_path.relative_to(ROOT)),
                        "station_id": str(station),
                        "issue": "nodata_or_implausible",
                        "n_nodata_sentinel": n_nodata,
                        "n_implausible_celsius": n_implausible,
                        "value_min": float(finite.min()) if len(finite) else None,
                        "value_max": float(finite.max()) if len(finite) else None,
                        "action": "convert_sentinel_to_na_quarantine_implausible_rebuild_eligibility",
                        "finding": "F01",
                    }
                )

    # SMHI station dailies
    smhi_dir = READY / "multi_agency_ingest" / "smhi" / "station_daily"
    if smhi_dir.is_dir():
        for csv_path in sorted(smhi_dir.glob("*.csv")):
            frame = pd.read_csv(csv_path)
            if "temperature_c" not in frame.columns:
                continue
            values = pd.to_numeric(frame["temperature_c"], errors="coerce")
            finite = values[np.isfinite(values)]
            n_implausible = int(((finite < TEMP_MIN) | (finite > TEMP_MAX)).sum())
            if n_implausible:
                rows.append(
                    {
                        "provider": "smhi",
                        "panel_path": str(csv_path.relative_to(ROOT)),
                        "station_id": csv_path.stem,
                        "issue": "implausible_celsius_unit_or_coding",
                        "n_nodata_sentinel": 0,
                        "n_implausible_celsius": n_implausible,
                        "value_min": float(finite.min()) if len(finite) else None,
                        "value_max": float(finite.max()) if len(finite) else None,
                        "action": "quarantine_until_source_unit_verified_no_guessed_rescale",
                        "finding": "F01",
                    }
                )

    # HubEau network identity
    stations_path = READY / "multi_agency_ingest" / "hubeau" / "stations.csv"
    if stations_path.is_file():
        st = pd.read_csv(stations_path, dtype={"station_id": str})
        for network_id, group in st.groupby("network_id"):
            lat = pd.to_numeric(group.get("latitude"), errors="coerce")
            lon = pd.to_numeric(group.get("longitude"), errors="coerce")
            ok = lat.notna() & lon.notna()
            span_km = 0.0
            if int(ok.sum()) >= 2:
                latv = np.deg2rad(lat.loc[ok].to_numpy(dtype=float))
                lonv = np.deg2rad(lon.loc[ok].to_numpy(dtype=float))
                for i in range(len(latv)):
                    dlat = latv - latv[i]
                    dlon = lonv - lonv[i]
                    a = np.sin(dlat / 2) ** 2 + np.cos(latv[i]) * np.cos(latv) * np.sin(dlon / 2) ** 2
                    dist = 6371.0 * 2 * np.arcsin(np.minimum(1.0, np.sqrt(a)))
                    span_km = max(span_km, float(np.nanmax(dist)))
            codes = group.get("hubeau_code_cours_eau")
            n_codes = int(pd.Series(codes).dropna().astype(str).nunique()) if codes is not None else 0
            if span_km > 200 or n_codes > 1:
                rows.append(
                    {
                        "provider": "hubeau",
                        "panel_path": str(stations_path.relative_to(ROOT)),
                        "station_id": ";".join(group["station_id"].astype(str)),
                        "issue": "homonym_or_wide_network",
                        "n_nodata_sentinel": 0,
                        "n_implausible_celsius": 0,
                        "value_min": None,
                        "value_max": None,
                        "network_id": str(network_id),
                        "span_km": span_km,
                        "n_distinct_watercourse_codes": n_codes,
                        "action": "split_by_code_cours_eau_or_spatial_cell_then_rebuild_donors",
                        "finding": "F08",
                    }
                )

    # Daily-statistic contract summary for primary transport providers
    prov = READY / "measurement_provenance_dictionary.csv"
    if prov.is_file():
        dictionary = pd.read_csv(prov)
        dictionary.to_csv(OUT / "measurement_provenance_dictionary_snapshot.csv", index=False)

    ledger = pd.DataFrame(rows)
    ledger.to_csv(OUT / "qc_ledger.csv", index=False)
    summary = {
        "n_issue_rows": int(len(ledger)),
        "by_finding": ledger["finding"].value_counts().to_dict() if len(ledger) else {},
        "by_provider": ledger["provider"].value_counts().to_dict() if len(ledger) else {},
        "n_usgs_nodata_cells": int(ledger.loc[ledger.provider.eq("usgs"), "n_nodata_sentinel"].sum())
        if len(ledger)
        else 0,
        "n_smhi_implausible_cells": int(
            ledger.loc[ledger.provider.eq("smhi"), "n_implausible_celsius"].sum()
        )
        if len(ledger)
        else 0,
        "policy": (
            "No guessed unit rescales. Sentinels -> NA. Implausible °C quarantined. "
            "HubEau homonyms split by official code or spatial cell. "
            "All downstream eligibility/donor/cases must be rebuilt after repair."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
