#!/usr/bin/env python3
"""Uniform QC pass over the ingested transport panels (pre-seal).

One documented, outcome-blind rule is applied to every provider panel:

    Core-warm-season (June-September) runs of >= 3 consecutive days at exactly
    0.0 degrees C are treated as missing (stuck/frozen sensor). Values are not
    deleted from the provider's raw cache; they are blanked in the QC'd panel.
    May is deliberately excluded: nival Nordic rivers can sit legitimately at
    0.0 C for days during snowmelt, and the first run of this rule blanked 200
    such May values in the SMHI and NVE panels before the window was narrowed.

Rationale: liquid river water held at exactly 0.0 C for several consecutive
summer days is physically implausible, and the UK EA ingest flagged two such
runs (one entirely inside a hottest-30 window). The rule is structural, applied
identically to every provider, and recorded before the transport panel is
sealed or scored. It cannot be tuned to an outcome because no outcome has been
computed for this panel.

Writes <provider>/networks_qc/ and <provider>/qc_report.csv.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

INGEST = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest"
WARM_MONTHS = (6, 7, 8, 9)
MIN_RUN = 3
FROZEN_VALUE = 0.0
# Do not guess unit conversions for out-of-range values (F01). Quarantine only.
TEMP_C_MIN = -5.0
TEMP_C_MAX = 50.0  # hot arid rivers can exceed 45 C; still far below coding failures
USGS_NODATA = -999999.0


def qc_series(series: pd.Series) -> tuple[pd.Series, int, dict[str, int]]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    out = values.copy()
    dropped = 0
    reasons = {"frozen_warm_zero_run": 0, "nodata_sentinel": 0, "implausible_celsius": 0}
    nodata = np.isfinite(out) & (out == USGS_NODATA)
    reasons["nodata_sentinel"] = int(nodata.sum())
    out[nodata] = np.nan
    dropped += int(nodata.sum())
    implausible = np.isfinite(out) & ((out < TEMP_C_MIN) | (out > TEMP_C_MAX))
    reasons["implausible_celsius"] = int(implausible.sum())
    out[implausible] = np.nan
    dropped += int(implausible.sum())
    warm = pd.Series(series.index.month).isin(WARM_MONTHS).to_numpy()
    run_start = None
    for i in range(len(out)):
        is_frozen = warm[i] and np.isfinite(out[i]) and out[i] == FROZEN_VALUE
        if is_frozen and run_start is None:
            run_start = i
        if (not is_frozen or i == len(out) - 1) and run_start is not None:
            end = i if not is_frozen else i + 1
            if end - run_start >= MIN_RUN:
                out[run_start:end] = np.nan
                n = end - run_start
                dropped += n
                reasons["frozen_warm_zero_run"] += n
            run_start = None
    return pd.Series(out, index=series.index), dropped, reasons


def main() -> int:
    report_rows: list[dict[str, object]] = []
    for provider_dir in sorted(p for p in INGEST.glob("*") if (p / "networks").is_dir()):
        provider = provider_dir.name
        out_root = provider_dir / "networks_qc"
        for network_dir in sorted((provider_dir / "networks").glob("*")):
            panel_path = network_dir / "daily_wide_temperature.csv"
            if not panel_path.is_file():
                continue
            panel = pd.read_csv(panel_path, parse_dates=["date"]).set_index("date")
            panel = panel.apply(pd.to_numeric, errors="coerce").sort_index()
            panel.columns = [str(c) for c in panel.columns]
            for station in panel.columns:
                cleaned, dropped, reasons = qc_series(panel[station])
                panel[station] = cleaned
                if dropped:
                    report_rows.append(
                        {
                            "provider": provider,
                            "network_id": network_dir.name,
                            "station_id": station,
                            "rule": (
                                f"nodata_or_implausible_celsius_or_"
                                f"core_warm_season_run_ge{MIN_RUN}_at_{FROZEN_VALUE}C"
                            ),
                            "n_values_blanked": int(dropped),
                            "n_nodata_sentinel": int(reasons["nodata_sentinel"]),
                            "n_implausible_celsius": int(reasons["implausible_celsius"]),
                            "n_frozen_warm_zero_run": int(reasons["frozen_warm_zero_run"]),
                        }
                    )
            target = out_root / network_dir.name
            target.mkdir(parents=True, exist_ok=True)
            panel.reset_index().to_csv(target / "daily_wide_temperature.csv", index=False)

    report = pd.DataFrame(report_rows)
    if report.empty:
        report = pd.DataFrame(
            columns=[
                "provider",
                "network_id",
                "station_id",
                "rule",
                "n_values_blanked",
                "n_nodata_sentinel",
                "n_implausible_celsius",
                "n_frozen_warm_zero_run",
            ]
        )
    for provider_dir in sorted(p for p in INGEST.glob("*") if (p / "networks_qc").is_dir()):
        block = report.loc[report["provider"].eq(provider_dir.name)]
        block.to_csv(provider_dir / "qc_report.csv", index=False)
    out = INGEST / "QC_SUMMARY.json"
    out.write_text(
        json.dumps(
            {
                "rule": (
                    "blank USGS-style -999999 sentinels; quarantine values outside "
                    f"[{TEMP_C_MIN}, {TEMP_C_MAX}] C without unit conversion; "
                    "core-warm-season (Jun-Sep) runs of >=3 consecutive days at exactly 0.0 C "
                    "are blanked as stuck-sensor values"
                ),
                "providers": sorted({row["provider"] for row in report_rows}),
                "n_stations_affected": int(report["station_id"].nunique()) if len(report) else 0,
                "n_values_blanked": int(report["n_values_blanked"].sum()) if len(report) else 0,
                "n_implausible_celsius": int(report.get("n_implausible_celsius", pd.Series(dtype=int)).sum())
                if len(report)
                else 0,
                "detail": report_rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
